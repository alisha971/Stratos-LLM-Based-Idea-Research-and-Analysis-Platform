from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.services.astra_evidence_repository import AstraEvidenceRepository
from app.services.embedding_service import EmbeddingService
from app.services.evidence_ranker import EvidenceRanker, section_intent
from app.utils.clarification_schema import research_directives as _directives_from_summary
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
# Stage 3f: of BUNDLE_SIZE, reserve at least this many slots for each of
# "challenges" and "supports" (when available) before filling the rest by
# fused score -- otherwise a lopsided retrieval makes a balanced section
# impossible no matter what the section-writer prompt asks for.
MIN_ITEMS_PER_STANCE = 3


def _fingerprint(text: str | None) -> str:
    """Text-prefix fallback fusion key, used only when an item has no real
    id (e.g. the Postgres disaster-recovery fallback, which was never
    chunked into `embeddings`). Same scheme EvidenceRanker uses for its own
    lexical dedup."""
    return (text or "").strip().lower()[:180]


def _fusion_key(*, explicit_id: Any, text: str | None) -> str:
    """The id two representations of the same chunk are joined on for RRF
    fusion. Prefers a real Astra document id (gap-closing plan Stage 5:
    lexical items now come from the `embeddings` collection too, via
    AstraEvidenceRepository.list_evidence_chunks, so they carry one) over
    the old text-prefix fingerprint, which could silently collide two
    distinct chunks sharing the same opening ~180 characters (repeated
    nav/header boilerplate surviving clean_html) and depended on an
    unenforced invariant that both writes came from identical chunking."""
    if explicit_id:
        return f"id:{explicit_id}"
    return f"fp:{_fingerprint(text)}"




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

        # Built once per report, not per section -- stance is a property
        # of the Source, not of any one section's ranking.
        stance_by_source = self._load_stance_by_source(report_id)

        bundles = []
        for section in sections:
            ranked_items = self._hybrid_rank_for_section(
                report_id=report_id,
                clarified_summary=session.clarified_summary,
                section_title=section.title,
                evidence_items=evidence_items,
                stance_by_source=stance_by_source,
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
    # Public entry point (gap-closing plan Stage 4/5): SectionWriterService's
    # evidence-retrieval fallback (bundle cache miss) calls this directly
    # rather than re-implementing a weaker version of the same ranking, so
    # report quality no longer depends on whether the bundle cache happened
    # to hit. Kept as a thin wrapper around the underscore-prefixed method
    # below -- rather than renaming it -- because a wide existing test
    # surface (tests/test_evidence_bundle_hybrid.py,
    # tests/harness/test_*.py) calls `_hybrid_rank_for_section` directly by
    # that name, always passing `stance_by_source` explicitly (often via a
    # `db=None` service, since those tests exercise pure ranking logic).
    #
    # The lazy stance_by_source load lives HERE, not in
    # `_hybrid_rank_for_section` itself -- that method's contract (a caller
    # who wants stance either passes it or gets none, never a surprise DB
    # query) stays exactly what that whole test suite already assumes.
    # --------------------------------------------------
    def hybrid_rank_for_section(
        self,
        *,
        report_id: str,
        clarified_summary: str,
        section_title: str,
        evidence_items: list[dict[str, Any]],
        stance_by_source: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if stance_by_source is None:
            stance_by_source = self._load_stance_by_source(report_id)

        return self._hybrid_rank_for_section(
            report_id=report_id,
            clarified_summary=clarified_summary,
            section_title=section_title,
            evidence_items=evidence_items,
            stance_by_source=stance_by_source,
        )

    # --------------------------------------------------
    # Hybrid ranking (gap-closing plan Stage 2f/2g): lexical (EvidenceRanker)
    # fused with semantic (EmbeddingService.find_similar) via Reciprocal
    # Rank Fusion, then diversified to drop near-duplicate chunks, then
    # stance-balanced/capped-per-source into the final bundle size.
    # --------------------------------------------------
    def _hybrid_rank_for_section(
        self,
        *,
        report_id: str,
        clarified_summary: str,
        section_title: str,
        evidence_items: list[dict[str, Any]],
        stance_by_source: dict[str, str] | None = None,
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
        lexical_by_key: dict[str, dict[str, Any]] = {}
        lexical_keys: list[str] = []
        for item in lexical_ranked:
            key = _fusion_key(explicit_id=item.get("chunk_id"), text=item.get("quote"))
            lexical_by_key[key] = item
            lexical_keys.append(key)

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
        semantic_by_key: dict[str, dict[str, Any]] = {}
        semantic_keys: list[str] = []
        for hit in semantic_hits:
            # Astra's own `_id` for this chunk document -- the same value
            # `list_evidence_chunks` surfaces as `chunk_id` after
            # EvidenceRanker normalization, so a chunk present on both
            # sides joins on this instead of a text-prefix fingerprint.
            key = _fusion_key(explicit_id=hit.get("_id"), text=hit.get("text"))
            if key in semantic_by_key:
                continue
            semantic_by_key[key] = hit
            semantic_keys.append(key)

        fused_order = fuse_and_sort([lexical_keys, semantic_keys])

        merged: list[dict[str, Any]] = []
        for key in fused_order:
            item = lexical_by_key.get(key)
            if item is None:
                # Astra's vector search found it, but lexical scoring
                # dropped it (score <= 0) or it wasn't in evidence_items at
                # all -- exactly the case hybrid ranking exists to catch.
                # Build the same normalized shape from the semantic hit so
                # downstream code (marker assignment, source cap) doesn't
                # need to know which side an item came from.
                item = self._item_from_semantic_hit(semantic_by_key[key])
            merged.append(item)

        diversified = diversify(
            merged,
            text_fn=lambda i: i.get("quote") or "",
            limit=len(merged),
        )

        selected = self._select_with_stance_slots(
            diversified,
            limit=BUNDLE_SIZE,
            max_per_source=MAX_CHUNKS_PER_SOURCE,
            stance_by_source=stance_by_source or {},
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

    def _select_with_stance_slots(
        self,
        items: list[dict[str, Any]],
        *,
        limit: int,
        max_per_source: int,
        stance_by_source: dict[str, str],
        min_per_stance: int = MIN_ITEMS_PER_STANCE,
    ) -> list[dict[str, Any]]:
        """Stage 3f: reserve up to `min_per_stance` slots for each of
        "challenges" and "supports" -- walking `items` (already ranked
        best-first) so the BEST-ranked item of each stance fills its slot
        -- before filling the rest of `limit` by fused rank regardless of
        stance. The per-source cap (Stage 2a) applies throughout; a stance
        slot is not an exemption from it, so a single lopsided source
        can't satisfy the whole reservation by itself beyond its cap."""
        selected: list[dict[str, Any]] = []
        # "Already selected in an earlier pass of this same `items` list" is
        # object identity, not text -- the stance loop and the fill loop
        # walk the identical dict objects. A 180-char text fingerprint here
        # (gap-closing plan Stage 5) would silently drop a genuinely
        # distinct chunk that merely shares an opening boilerplate prefix
        # with one already taken; near-duplicate suppression already
        # happened in diversify() upstream.
        selected_ids: set[int] = set()
        per_source_count: dict[str, int] = {}

        def stance_of(item: dict[str, Any]) -> str:
            source_id = item.get("source_id")
            return stance_by_source.get(source_id, "neutral") if source_id else "neutral"

        def try_take(item: dict[str, Any]) -> bool:
            source_id = item.get("source_id")
            if source_id:
                count = per_source_count.get(source_id, 0)
                if count >= max_per_source:
                    return False
                per_source_count[source_id] = count + 1
            selected.append(item)
            selected_ids.add(id(item))
            return True

        for target_stance in ("challenges", "supports"):
            taken = 0
            for item in items:
                if len(selected) >= limit or taken >= min_per_stance:
                    break
                if id(item) in selected_ids or stance_of(item) != target_stance:
                    continue
                if try_take(item):
                    taken += 1

        for item in items:
            if len(selected) >= limit:
                break
            if id(item) in selected_ids:
                continue
            try_take(item)

        return selected

    def _load_stance_by_source(self, report_id: str) -> dict[str, str]:
        rows = (
            self.db.query(models.Source.id, models.Source.stance)
            .filter_by(report_id=report_id)
            .all()
        )
        return {source_id: stance for source_id, stance in rows if stance}

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
