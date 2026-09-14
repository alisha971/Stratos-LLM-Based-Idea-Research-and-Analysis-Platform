from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.llm.json_parse import parse_json_object
from app.llm.prompts import SECTION_WRITER_PROMPT
from app.services.astra_evidence_repository import AstraEvidenceRepository
from app.services.evidence_bundle_service import EvidenceBundleService
from app.utils.clarification_schema import writer_view


TITLE_KEYWORDS = {
    "problem": {"problem", "pain", "validation", "context", "need", "workaround"},
    "persona": {"user", "users", "persona", "personas", "customer", "audience", "target"},
    # Fix-audit Part 1: widened so a genuine "Existing Solutions" section
    # (which must name actual products to describe them) has a realistic
    # chance of scoring on its own bucket instead of only Competitor
    # Landscape's -- previously 6 words, half of them inflections of each
    # other, versus Competitor Landscape's product/pricing/feature bucket
    # that any honest write-up of existing solutions necessarily also hits.
    "solutions": {
        "solution", "solutions", "alternative", "alternatives", "existing",
        "workaround", "product", "products", "tool", "tools", "platform",
        "vendor", "incumbent", "offering", "approach",
    },
    "competitor": {"competitor", "competitors", "landscape", "pricing", "feature", "features"},
    "trend": {"market", "industry", "trend", "trends", "news", "growth", "adoption"},
    # Key is "opportunit" (a stem), not "opportunity": the outline's actual
    # title is "Opportunities & Gaps", and "opportunity" is NOT a substring
    # of "opportunities" (they diverge at the 11th character), so the old
    # key silently never matched -- this section's own vocabulary fell
    # through to the generic 2-word {opportunities, gaps} bucket, which is
    # too small to ever score >=3 and be picked as a drift target.
    "opportunit": {"opportunity", "opportunities", "gap", "gaps", "differentiation", "positioning"},
    "risk": {"risk", "risks", "question", "questions", "unknown", "constraint", "constraints"},
    "technical": {"technical", "feasibility", "architecture", "integration", "implementation"},
    "regulatory": {"regulatory", "compliance", "privacy", "legal", "policy"},
    "gtm": {"go-to-market", "market", "sales", "distribution", "positioning"},
}

STOPWORDS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",
    "in",
    "on",
    "with",
}

# Terms that identify the outline's gaps section. "gap"/"gaps" is deliberately
# excluded so "Opportunities & Gaps" — a findings section — does not match.
GAPS_TITLE_TERMS = {
    "risk",
    "risks",
    "open",
    "question",
    "questions",
    "unknown",
    "unknowns",
    "limitation",
    "limitations",
}


def _looks_like_gaps_title(title: str) -> bool:
    words = set(re.findall(r"[a-z]+", (title or "").lower()))
    return bool(words & GAPS_TITLE_TERMS)


def is_gaps_section(title: str, outline_sections: list[Any]) -> bool:
    """Whether this section should carry what research could not establish.

    The outline prompt mandates a "Risks & Open Questions" section, but the
    model can rename it. If nothing in the outline looks like one, the last
    section carries the gaps rather than dropping them.
    """
    if _looks_like_gaps_title(title):
        return True

    titles = [section.title for section in outline_sections]
    if any(_looks_like_gaps_title(item) for item in titles):
        return False

    return bool(titles) and titles[-1] == title


class SectionWriterService:
    def __init__(
        self,
        db: Session,
        astra_repository: AstraEvidenceRepository | None = None,
    ) -> None:
        self.db = db
        self.astra_repository = astra_repository or AstraEvidenceRepository()

    def build_section_context(self, report_id: str, section_id: str) -> dict[str, Any]:
        report = self.db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        section = (
            self.db.query(models.Section)
            .filter_by(id=section_id, report_id=report_id)
            .first()
        )
        if not section:
            raise ValueError("Section not found")

        session = self.db.query(models.Session).filter_by(id=report.session_id).first()
        if not session or not session.clarified_summary:
            raise ValueError("Clarified summary missing")

        outline_sections = (
            self.db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )

        clarified_summary = session.clarified_summary
        astra_items = self._fetch_astra_items(
            report_id, section.id, section.title, clarified_summary
        )
        fallback_items = self._fetch_postgres_fallback_items(
            report_id, section.title, clarified_summary
        )
        evidence_items = astra_items or fallback_items
        if not evidence_items:
            raise ValueError("Missing evidence bundle")

        citation_map = self._build_citation_marker_map(evidence_items)

        context = {
            "report": {
                "id": report.id,
                "topic": report.topic,
                # Projected: established idea facts only. Research scaffolding
                # (directives, knowledge gaps, unresolved fields) is dropped so
                # the writer cannot quote it back as if it were a finding.
                "clarified_summary": writer_view(session.clarified_summary),
            },
            "section": {
                "id": section.id,
                "title": section.title,
                "order_index": section.order_index,
            },
            "outline_titles": [item.title for item in outline_sections],
            "evidence_items": evidence_items,
            "citation_map": citation_map,
            "source_mode": "astra" if astra_items else "postgres_fallback",
        }

        # The gaps section is the one place research shortfalls belong: it is
        # told what could not be established so the report says so plainly
        # instead of quietly omitting it.
        if is_gaps_section(section.title, outline_sections):
            context["unresolved_gaps"] = EvidenceBundleService(
                self.db,
                astra_repository=self.astra_repository,
            ).unresolved_directives(report_id, session.clarified_summary)

        return context

    def generate_section_draft(
        self,
        context: dict[str, Any],
        repair_reason: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        # 2026-09-14 remediation Phase 3: section_writer is migrated onto
        # the scheduler-backed multi-provider dispatch (Gemini first,
        # falling back to Groq -- see FEDERATED_ROUTES in
        # app/llm/client_federated.py for the live-verification story
        # behind this choice). app/llm/client.py's generate_chat (Groq-only,
        # TASK_ROUTES-driven) is unaffected and still used by every other
        # task -- this is the one call site actually migrated so far.
        from app.llm.client_federated import generate_chat_federated

        prompt = self._build_prompt(context)
        if repair_reason:
            prompt += (
                "\n\nREPAIR REQUIRED:\n"
                f"{repair_reason}\n"
                "Regenerate the full JSON so the section is valid."
            )

        raw_output = generate_chat_federated(
            messages=[{"role": "system", "content": prompt}],
            temperature=temperature,
            task="section_writer",
        )
        return self._parse_json(raw_output)

    def validate_section_draft(
        self,
        draft: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        """Fatal, correctness-only checks (fix-audit Part 1). Everything
        here is provable from the draft's own structure: a section that
        fails one of these is malformed or ungrounded, not just
        off-topic. Topical alignment is a quality *signal*, not a
        correctness invariant -- see `assess_section_quality`, which must
        be called separately and never raises."""
        chunks = draft.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise ValueError("Section draft missing chunks")

        alignment = draft.get("section_alignment_summary")
        if not isinstance(alignment, str) or not alignment.strip():
            raise ValueError("Section draft missing section_alignment_summary")

        citation_map = context["citation_map"]
        allowed_markers = set(citation_map)
        allowed_source_ids = {
            item["source_id"]
            for item in citation_map.values()
            if item.get("source_id")
        }

        for expected_index, chunk in enumerate(chunks, start=1):
            if chunk.get("chunk_index") != expected_index:
                raise ValueError("Chunk indexes must be deterministic and sequential")

            text = chunk.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Chunk text is empty")
            if len(text) > 2500:
                raise ValueError("Chunk text exceeds maximum length")

            text_markers = set(re.findall(r"\[(CIT-\d{3})\]", text))
            if not text_markers:
                raise ValueError("Chunk has no inline citations")
            if not text_markers.issubset(allowed_markers):
                raise ValueError("Chunk references unknown citation marker")

            citations = chunk.get("citations")
            if not isinstance(citations, list) or not citations:
                raise ValueError("Chunk citations array is empty")

            citation_markers = set()
            for citation in citations:
                marker = citation.get("marker")
                source_id = citation.get("source_id")
                if marker not in allowed_markers:
                    raise ValueError("Citation references unknown marker")
                if source_id not in allowed_source_ids:
                    raise ValueError("Citation references unknown source_id")
                citation_markers.add(marker)

            if not text_markers.issubset(citation_markers):
                raise ValueError("Inline citations missing from citations array")

    def assess_section_quality(
        self,
        draft: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        """Non-fatal quality signals (fix-audit Part 1). Topical-alignment
        keyword heuristics that used to be enforced as hard validators in
        `validate_section_draft` -- a keyword-overlap heuristic is a
        useful smell for a human (or a later automated pass) to look at,
        but it cannot distinguish "on-topic prose that happens to share
        vocabulary with a neighboring section" from genuine drift, so it
        must never be able to drop a section from the shipped report.
        Call only after `validate_section_draft` has passed; returns an
        empty list when nothing looks off.
        """
        section_title = context["section"]["title"]
        chunks = draft.get("chunks") or []
        alignment = str(draft.get("section_alignment_summary") or "")
        all_text = " ".join([alignment] + [str(c.get("text", "")) for c in chunks])

        findings: list[str] = []

        title_finding = self._title_match_finding(section_title, all_text)
        if title_finding:
            findings.append(title_finding)

        drift_finding = self._drift_finding(
            section_title, context.get("outline_titles", []), all_text
        )
        if drift_finding:
            findings.append(drift_finding)

        return findings

    def persist_section_chunks(
        self,
        report_id: str,
        section_id: str,
        chunks: list[dict[str, Any]],
        citation_map: dict[str, dict[str, Any]],
    ) -> list[str]:
        existing_chunks = (
            self.db.query(models.Chunk)
            .filter_by(section_id=section_id)
            .all()
        )
        for chunk in existing_chunks:
            self.db.query(models.Citation).filter_by(chunk_id=chunk.id).delete()
        self.db.query(models.Chunk).filter_by(section_id=section_id).delete()
        self.db.flush()

        chunk_ids: list[str] = []
        for chunk_data in chunks:
            chunk = models.Chunk(
                id=str(uuid.uuid4()),
                section_id=section_id,
                chunk_text=chunk_data["text"],
                chunk_index=chunk_data["chunk_index"],
            )
            self.db.add(chunk)
            self.db.flush()
            chunk_ids.append(chunk.id)

            for citation_data in chunk_data.get("citations", []):
                marker = citation_data["marker"]
                source_id = citation_data["source_id"]
                evidence = citation_map.get(marker, {})
                self.db.add(
                    models.Citation(
                        id=str(uuid.uuid4()),
                        chunk_id=chunk.id,
                        source_id=source_id,
                        citation_marker=marker,
                        quote=citation_data.get("quote") or evidence.get("quote"),
                    )
                )

        self.db.commit()
        return chunk_ids

    def _fetch_astra_items(
        self,
        report_id: str,
        section_id: str,
        section_title: str,
        clarified_summary: str,
    ) -> list[dict[str, Any]]:
        bundle = self.astra_repository.get_evidence_bundle(
            report_id=report_id,
            section_id=section_id,
        )
        if bundle and isinstance(bundle.get("items"), list):
            # Already fully ranked by EvidenceBundleService (hybrid lexical
            # + semantic fusion, diversified, stance-balanced, source-capped)
            # -- do NOT re-rank here. This used to be re-sorted by the flat
            # keyword-count `_relevance_score` below, which silently
            # discarded that ordering even on a cache HIT.
            return self._finalize_evidence_items(bundle["items"], "astra_bundle")

        raw_items: list[dict[str, Any]] = []
        raw_items.extend(self.astra_repository.fetch_evidence(report_id, section_title))
        raw_items.extend(self.astra_repository.fetch_trend_items(report_id, section_title))
        raw_items.extend(
            self.astra_repository.fetch_competitor_insights(report_id, section_title)
        )
        ranked = self._hybrid_rank(
            report_id=report_id,
            clarified_summary=clarified_summary,
            section_title=section_title,
            evidence_items=raw_items,
        )
        return self._finalize_evidence_items(ranked, "astra")

    def _fetch_postgres_fallback_items(
        self,
        report_id: str,
        section_title: str,
        clarified_summary: str,
    ) -> list[dict[str, Any]]:
        sources = (
            self.db.query(models.Source)
            .filter_by(report_id=report_id)
            .order_by(models.Source.created_at.asc())
            .all()
        )

        raw_items: list[dict[str, Any]] = []
        for source in sources:
            for evidence in source.evidence:
                raw_items.append(
                    {
                        "source_id": source.id,
                        "url": source.url,
                        "domain": source.domain,
                        "title": source.domain or source.url,
                        "type": source.type,
                        "quote": evidence.snippet,
                        "text": evidence.snippet,
                    }
                )

        ranked = self._hybrid_rank(
            report_id=report_id,
            clarified_summary=clarified_summary,
            section_title=section_title,
            evidence_items=raw_items,
        )
        return self._finalize_evidence_items(ranked, "postgres")

    def _hybrid_rank(
        self,
        *,
        report_id: str,
        clarified_summary: str,
        section_title: str,
        evidence_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Routes both cache-miss retrieval paths through the same hybrid
        ranker EvidenceBundleService uses for the happy path (gap-closing
        plan Stage 4), instead of the old flat keyword-count
        `_relevance_score` sort -- so evidence quality no longer depends on
        whether the per-section bundle cache happened to hit. Also picks up
        Stage 2a's per-source cap (MAX_CHUNKS_PER_SOURCE) and Stage 3f's
        stance-slot reservation, neither of which the old fallback had."""
        return EvidenceBundleService(
            self.db, astra_repository=self.astra_repository
        ).hybrid_rank_for_section(
            report_id=report_id,
            clarified_summary=clarified_summary,
            section_title=section_title,
            evidence_items=evidence_items,
        )

    def _finalize_evidence_items(
        self,
        items: list[dict[str, Any]],
        source_mode: str,
    ) -> list[dict[str, Any]]:
        """Adds the two fields the ranker's normalized shape doesn't carry
        (`astra_evidence_id`, `source_mode`) and drops anything unusable
        (no source_id/quote) or duplicate. Does NOT re-rank, re-sort, or
        re-cap -- `items` already arrived in the order and size (<=
        evidence_bundle_service.BUNDLE_SIZE) whichever ranking path
        produced, and re-deriving that here is exactly the bug this method
        replaces (see _fetch_astra_items)."""
        finalized: list[dict[str, Any]] = []
        seen_quotes: set[str] = set()
        for item in items:
            source_id = item.get("source_id")
            quote = item.get("quote") or item.get("snippet") or item.get("text")
            if not source_id or not quote:
                continue

            quote = str(quote).strip()
            fingerprint = quote.lower()[:180]
            if fingerprint in seen_quotes:
                continue
            seen_quotes.add(fingerprint)

            finalized.append(
                {
                    "source_id": str(source_id),
                    "astra_evidence_id": item.get("evidence_id")
                    or item.get("astra_evidence_id")
                    or item.get("_id"),
                    "marker": item.get("marker"),
                    "section_relevance_score": item.get("section_relevance_score"),
                    "reason": item.get("reason"),
                    "title": item.get("title") or item.get("domain") or item.get("url"),
                    "url": item.get("url"),
                    "domain": item.get("domain"),
                    "type": item.get("type") or source_mode,
                    "quote": quote[:1200],
                    "source_mode": source_mode,
                }
            )

        return finalized

    def _build_citation_marker_map(
        self,
        evidence_items: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        marker_map: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(evidence_items, start=1):
            marker = item.get("marker") or f"CIT-{index:03d}"
            item["marker"] = marker
            marker_map[marker] = item
        return marker_map

    def _build_prompt(self, context: dict[str, Any]) -> str:
        evidence_blocks = []
        for marker, item in context["citation_map"].items():
            evidence_blocks.append(
                "\n".join(
                    [
                        f"[{marker}]",
                        f"source_id: {item['source_id']}",
                        f"astra_evidence_id: {item.get('astra_evidence_id')}",
                        f"title: {item.get('title')}",
                        f"url: {item.get('url')}",
                        f"quote: {item['quote']}",
                    ]
                )
            )

        return (
            SECTION_WRITER_PROMPT.replace(
                "{{SECTION_TITLE}}",
                context["section"]["title"],
            )
            .replace(
                "{{OUTLINE_TITLES}}",
                json.dumps(context.get("outline_titles", [])),
            )
            .replace(
                "{{REPORT_CONTEXT}}",
                json.dumps(context["report"], indent=2),
            )
            .replace("{{EVIDENCE_BLOCKS}}", "\n\n".join(evidence_blocks))
            .replace(
                "{{UNRESOLVED_GAPS}}",
                json.dumps(context.get("unresolved_gaps") or [], indent=2),
            )
        )

    def _parse_json(self, raw_output: str) -> dict[str, Any]:
        return parse_json_object(raw_output, label="Section Writer")

    def _matches_section_title(self, section_title: str, text: str) -> bool:
        keywords = self._keywords_for_title(section_title)
        if not keywords:
            return True

        return bool(self._keyword_hits(text, keywords))

    def _title_match_finding(self, section_title: str, text: str) -> str | None:
        if self._matches_section_title(section_title, text):
            return None
        return (
            f'Section content does not use any vocabulary associated with '
            f'"{section_title}"'
        )

    def _drift_finding(
        self,
        section_title: str,
        outline_titles: list[str],
        text: str,
    ) -> str | None:
        """Fix-audit Part 1: adjacent business-report sections legitimately
        share vocabulary -- an honest "Existing Solutions" section must
        name products, features and prices, which also scores on
        Competitor Landscape's bucket, and that overlap alone must not be
        flagged. Only surfaces when another section's vocabulary clearly
        dominates this one's own (at least double, and at least 3 distinct
        hits) -- a real take-over, not ordinary overlap. Reports the
        specific competing title and the overlapping words so the reason
        is actionable rather than a bare "drifts" label.
        """
        current_keywords = self._keywords_for_title(section_title)
        current_hits = self._keyword_hits(text, current_keywords)
        current_score = len(current_hits)

        best_title: str | None = None
        best_hits: set[str] = set()
        for other_title in outline_titles:
            if other_title == section_title:
                continue
            other_hits = self._keyword_hits(text, self._keywords_for_title(other_title))
            if (
                len(other_hits) >= 3
                and len(other_hits) >= 2 * current_score
                and len(other_hits) > len(best_hits)
            ):
                best_title, best_hits = other_title, other_hits

        if not best_title:
            return None

        if current_score:
            self_desc = f"used only its own terms: {', '.join(sorted(current_hits))}"
        else:
            self_desc = f'used none of the vocabulary for "{section_title}"'

        return (
            f'Section content leans toward "{best_title}" '
            f"(matched: {', '.join(sorted(best_hits))}); {self_desc}"
        )

    def _keywords_for_title(self, title: str) -> set[str]:
        normalized = title.lower()
        for key, keywords in TITLE_KEYWORDS.items():
            if key in normalized:
                return keywords

        return {
            word
            for word in re.findall(r"[a-zA-Z][a-zA-Z-]+", normalized)
            if word not in STOPWORDS
        }

    def _keyword_hits(self, text: str, keywords: set[str]) -> set[str]:
        words = set(re.findall(r"[a-zA-Z][a-zA-Z-]+", text.lower()))
        return words & keywords

    def _keyword_score(self, text: str, keywords: set[str]) -> int:
        return len(self._keyword_hits(text, keywords))
