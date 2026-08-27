from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.services.astra_evidence_repository import AstraEvidenceRepository
from app.services.embedding_service import EmbeddingService
from app.services.evidence_ranker import EvidenceRanker, section_intent
from app.utils.ranking_fusion import diversify, fuse_and_sort

logger = logging.getLogger(__name__)

# Per-section bundle size and the Stage 2a per-source contribution cap --
# without the latter, one long page chunked into a dozen pieces could fill
# an entire bundle by itself.
BUNDLE_SIZE = 12
MAX_CHUNKS_PER_SOURCE = 3
# How many candidates the semantic side contributes before fusion -- wider
# than BUNDLE_SIZE so RRF/diversify/the source cap all have real pools to
# work with, not just the lexical top-12 re-ordered.
SEMANTIC_CANDIDATE_POOL = 25


def _fingerprint(text: str | None) -> str:
    """Same scheme EvidenceRanker already uses for lexical dedup --
    reused here as the fusion key between the lexical items (from
    Postgres/Astra `evidence`) and the semantic hits (from the separate
    Astra `embeddings` collection). The two collections don't share a
    chunk-level id, but both are populated from the identical chunk_text()
    output at ingestion time, so matching on normalized text is exact for
    a chunk present on both sides -- not a fuzzy join."""
    return (text or "").strip().lower()[:180]


def _directives_from_summary(clarified_summary: Any) -> list[str]:
    data = clarified_summary
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return []
    if not isinstance(data, dict):
        return []

    directives = data.get("research_directives")
    if isinstance(directives, str):
        try:
            directives = json.loads(directives)
        except (ValueError, TypeError):
            return []

    if not isinstance(directives, list):
        return []

    return [item.strip() for item in directives if isinstance(item, str) and item.strip()]


class EvidenceBundleService:
    def __init__(
        self,
        db: Session,
        astra_repository: AstraEvidenceRepository | None = None,
        ranker: EvidenceRanker | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.astra_repository = astra_repository or AstraEvidenceRepository()
        self.ranker = ranker or EvidenceRanker()
        self.embedding_service = embedding_service or EmbeddingService(
            self.astra_repository
        )

    def generate_bundles_for_report(self, report_id: str) -> list[dict[str, Any]]:
        report = self.db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        session = self.db.query(models.Session).filter_by(id=report.session_id).first()
        if not session or not session.clarified_summary:
            raise ValueError("Clarified summary missing")

        sections = (
            self.db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )
        if not sections:
            raise ValueError("No sections found")

        evidence_items = self._load_evidence_items(report_id)
        if not evidence_items:
            logger.warning("[BUNDLE] No evidence found for report_id=%s", report_id)
            return []

        bundles = []
        for section in sections:
            ranked_items = self._hybrid_rank_for_section(
                report_id=report_id,
                clarified_summary=session.clarified_summary,
                section_title=section.title,
                evidence_items=evidence_items,
            )
            if not ranked_items:
                logger.warning(
                    "[BUNDLE] No ranked evidence for report_id=%s section_id=%s",
                    report_id,
                    section.id,
                )
                continue

            bundle = {
                "bundle_id": str(uuid.uuid4()),
                "report_id": report_id,
                "section_id": section.id,
                "section_title": section.title,
                "items": ranked_items,
                "created_at": datetime.utcnow().isoformat(),
            }
            self.astra_repository.save_evidence_bundle(bundle)
            bundles.append(bundle)

        return bundles

    # --------------------------------------------------
    # Hybrid ranking (gap-closing plan Stage 2f/2g): lexical (EvidenceRanker)
    # fused with semantic (EmbeddingService.find_similar) via Reciprocal
    # Rank Fusion, then diversified to drop near-duplicate chunks, then
    # capped per-source and to the final bundle size.
    # --------------------------------------------------
    def _hybrid_rank_for_section(
        self,
        *,
        report_id: str,
        clarified_summary: str,
        section_title: str,
        evidence_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Lexical: unlimited here (limit=len(...)) -- the final BUNDLE_SIZE
        # cap is applied once, after fusion, not before it. Capping here
        # too would let lexical veto anything semantic-only found.
        lexical_ranked = self.ranker.rank_for_section(
            clarified_summary=clarified_summary,
            section_title=section_title,
            evidence_items=evidence_items,
            limit=len(evidence_items) or 1,
        )
        lexical_by_fp = {_fingerprint(item.get("quote")): item for item in lexical_ranked}
        lexical_ids = [_fingerprint(item.get("quote")) for item in lexical_ranked]

        # Semantic: section_intent() (not the raw section title) is the
        # query -- "Risks & Open Questions" embedded literally would just
        # match other section-title-shaped text, not the risks themselves.
        # find_similar already fails soft to [] (Astra down, NVIDIA hiccup,
        # or nothing embedded yet for this report), which degrades the
        # fusion below to pure lexical order -- see Stage 2d.
        semantic_hits = self.embedding_service.find_similar(
            report_id=report_id,
            query_text=section_intent(section_title),
            limit=SEMANTIC_CANDIDATE_POOL,
        )
        semantic_by_fp: dict[str, dict[str, Any]] = {}
        semantic_ids: list[str] = []
        for hit in semantic_hits:
            fp = _fingerprint(hit.get("text"))
            if not fp or fp in semantic_by_fp:
                continue
            semantic_by_fp[fp] = hit
            semantic_ids.append(fp)

        fused_order = fuse_and_sort([lexical_ids, semantic_ids])

        merged: list[dict[str, Any]] = []
        for fp in fused_order:
            item = lexical_by_fp.get(fp)
            if item is None:
                # Astra's vector search found it, but lexical scoring
                # dropped it (score <= 0) or it wasn't in evidence_items at
                # all -- exactly the case hybrid ranking exists to catch.
                # Build the same normalized shape from the semantic hit so
                # downstream code (marker assignment, source cap) doesn't
                # need to know which side an item came from.
                item = self._item_from_semantic_hit(semantic_by_fp[fp])
            merged.append(item)

        diversified = diversify(
            merged,
            text_fn=lambda i: i.get("quote") or "",
            limit=len(merged),
        )

        selected = self._select_with_source_cap(
            diversified,
            limit=BUNDLE_SIZE,
            max_per_source=MAX_CHUNKS_PER_SOURCE,
        )

        for index, item in enumerate(selected, start=1):
            item["marker"] = f"CIT-{index:03d}"

        return selected

    def _item_from_semantic_hit(self, hit: dict[str, Any]) -> dict[str, Any]:
        return {
            "evidence_id": hit.get("evidence_id") or hit.get("_id"),
            "source_id": hit.get("source_id"),
            "url": hit.get("url"),
            "domain": hit.get("domain"),
            "title": hit.get("domain") or hit.get("url"),
            "type": hit.get("content_type", "web"),
            "quote": hit.get("text"),
            "section_relevance_score": 0.0,
            "reason": "semantic_only",
        }

    def _select_with_source_cap(
        self,
        items: list[dict[str, Any]],
        *,
        limit: int,
        max_per_source: int,
    ) -> list[dict[str, Any]]:
        """Walk `items` (already ranked best-first) taking up to `limit`,
        skipping any item whose source has already contributed
        `max_per_source` -- so one long page chunked into a dozen pieces
        can't fill an entire bundle by itself (Stage 2a)."""
        selected: list[dict[str, Any]] = []
        per_source_count: dict[str, int] = {}

        for item in items:
            if len(selected) >= limit:
                break
            source_id = item.get("source_id")
            if source_id:
                count = per_source_count.get(source_id, 0)
                if count >= max_per_source:
                    continue
                per_source_count[source_id] = count + 1
            selected.append(item)

        return selected

    def unresolved_directives(
        self,
        report_id: str,
        clarified_summary: Any,
        min_overlap: int = 2,
    ) -> list[str]:
        """Research directives the gathered evidence does not support.

        Computed at write time rather than stored, so no schema migration is
        needed. Scores each directive's keywords against everything the
        research stage collected; a directive with almost no lexical footprint
        in the corpus is one the search could not answer.
        """
        directives = _directives_from_summary(clarified_summary)
        if not directives:
            return []

        evidence_items = self._load_evidence_items(report_id)
        if not evidence_items:
            # Nothing was gathered at all — every directive is unanswered.
            return directives

        haystack = " ".join(
            " ".join(
                str(item.get(key, ""))
                for key in ("title", "quote", "text", "domain", "url")
            )
            for item in evidence_items
        ).lower()

        unresolved = []
        for directive in directives:
            terms = self.ranker.keywords(directive)
            if not terms:
                continue
            matches = sum(1 for term in terms if term in haystack)
            if matches < min_overlap:
                unresolved.append(directive)

        return unresolved

    def _load_evidence_items(self, report_id: str) -> list[dict[str, Any]]:
        astra_items = self.astra_repository.fetch_evidence(report_id, section_title="")
        if astra_items:
            return astra_items

        return self._load_postgres_evidence_items(report_id)

    def _load_postgres_evidence_items(self, report_id: str) -> list[dict[str, Any]]:
        sources = (
            self.db.query(models.Source)
            .filter_by(report_id=report_id)
            .order_by(models.Source.created_at.asc())
            .all()
        )

        items: list[dict[str, Any]] = []
        for source in sources:
            for evidence in source.evidence:
                items.append(
                    {
                        "evidence_id": None,
                        "source_id": source.id,
                        "url": source.url,
                        "domain": source.domain,
                        "title": source.domain or source.url,
                        "type": source.type,
                        "quote": evidence.snippet,
                        "text": evidence.snippet,
                    }
                )

        return items
