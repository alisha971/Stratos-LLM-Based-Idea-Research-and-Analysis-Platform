from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.llm.prompts import SECTION_WRITER_PROMPT
from app.services.astra_evidence_repository import AstraEvidenceRepository


TITLE_KEYWORDS = {
    "problem": {"problem", "pain", "validation", "context", "need", "workaround"},
    "persona": {"user", "users", "persona", "personas", "customer", "audience", "target"},
    "solutions": {"solution", "solutions", "alternative", "alternatives", "existing", "workaround"},
    "competitor": {"competitor", "competitors", "landscape", "pricing", "feature", "features"},
    "trend": {"market", "industry", "trend", "trends", "news", "growth", "adoption"},
    "opportunity": {"opportunity", "opportunities", "gap", "gaps", "differentiation", "positioning"},
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

        astra_items = self._fetch_astra_items(report_id, section.id, section.title)
        fallback_items = self._fetch_postgres_fallback_items(report_id, section.title)
        evidence_items = astra_items or fallback_items
        if not evidence_items:
            raise ValueError("Missing evidence bundle")

        citation_map = self._build_citation_marker_map(evidence_items)

        return {
            "report": {
                "id": report.id,
                "topic": report.topic,
                "clarified_summary": session.clarified_summary,
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

    def generate_section_draft(
        self,
        context: dict[str, Any],
        repair_reason: str | None = None,
    ) -> dict[str, Any]:
        from app.llm.client import generate_chat

        prompt = self._build_prompt(context)
        if repair_reason:
            prompt += (
                "\n\nREPAIR REQUIRED:\n"
                f"{repair_reason}\n"
                "Regenerate the full JSON so the section is valid."
            )

        raw_output = generate_chat(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2,
            task="section_writer",
        )
        return self._parse_json(raw_output)

    def validate_section_draft(
        self,
        draft: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        chunks = draft.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise ValueError("Section draft missing chunks")

        alignment = draft.get("section_alignment_summary")
        if not isinstance(alignment, str) or not alignment.strip():
            raise ValueError("Section draft missing section_alignment_summary")

        section_title = context["section"]["title"]
        all_text = " ".join(
            [alignment] + [str(chunk.get("text", "")) for chunk in chunks]
        )
        if not self._matches_section_title(section_title, all_text):
            raise ValueError("Section content does not match section title")

        if self._drifts_to_other_section(
            section_title,
            context.get("outline_titles", []),
            all_text,
        ):
            raise ValueError("Section content drifts into another outline section")

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
    ) -> list[dict[str, Any]]:
        bundle = self.astra_repository.get_evidence_bundle(
            report_id=report_id,
            section_id=section_id,
        )
        if bundle and isinstance(bundle.get("items"), list):
            return self._normalize_evidence_items(
                bundle["items"],
                section_title,
                "astra_bundle",
            )

        raw_items: list[dict[str, Any]] = []
        raw_items.extend(self.astra_repository.fetch_evidence(report_id, section_title))
        raw_items.extend(self.astra_repository.fetch_trend_items(report_id, section_title))
        raw_items.extend(
            self.astra_repository.fetch_competitor_insights(report_id, section_title)
        )
        return self._normalize_evidence_items(raw_items, section_title, "astra")

    def _fetch_postgres_fallback_items(
        self,
        report_id: str,
        section_title: str,
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

        return self._normalize_evidence_items(raw_items, section_title, "postgres")

    def _normalize_evidence_items(
        self,
        raw_items: list[dict[str, Any]],
        section_title: str,
        source_mode: str,
    ) -> list[dict[str, Any]]:
        ranked = sorted(
            raw_items,
            key=lambda item: self._relevance_score(section_title, item),
            reverse=True,
        )

        normalized: list[dict[str, Any]] = []
        seen_quotes: set[str] = set()
        for item in ranked:
            source_id = item.get("source_id")
            quote = item.get("quote") or item.get("snippet") or item.get("text")
            if not source_id or not quote:
                continue

            quote = str(quote).strip()
            fingerprint = quote.lower()[:180]
            if fingerprint in seen_quotes:
                continue
            seen_quotes.add(fingerprint)

            normalized.append(
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

            if len(normalized) >= 15:
                break

        return normalized

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
        )

    def _parse_json(self, raw_output: str) -> dict[str, Any]:
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError("Section Writer LLM output is not valid JSON") from exc

        if not isinstance(data, dict):
            raise ValueError("Section Writer LLM output must be a JSON object")
        return data

    def _matches_section_title(self, section_title: str, text: str) -> bool:
        keywords = self._keywords_for_title(section_title)
        if not keywords:
            return True

        words = set(re.findall(r"[a-zA-Z][a-zA-Z-]+", text.lower()))
        return bool(words.intersection(keywords))

    def _drifts_to_other_section(
        self,
        section_title: str,
        outline_titles: list[str],
        text: str,
    ) -> bool:
        current_keywords = self._keywords_for_title(section_title)
        current_score = self._keyword_score(text, current_keywords)

        for other_title in outline_titles:
            if other_title == section_title:
                continue
            other_keywords = self._keywords_for_title(other_title)
            other_score = self._keyword_score(text, other_keywords)
            if other_score >= 3 and other_score > current_score + 1:
                return True

        return False

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

    def _keyword_score(self, text: str, keywords: set[str]) -> int:
        words = set(re.findall(r"[a-zA-Z][a-zA-Z-]+", text.lower()))
        return len(words.intersection(keywords))

    def _relevance_score(self, section_title: str, item: dict[str, Any]) -> int:
        haystack = " ".join(
            str(item.get(key, ""))
            for key in ("title", "type", "quote", "snippet", "text", "domain")
        ).lower()
        keywords = self._keywords_for_title(section_title)
        return sum(1 for keyword in keywords if keyword in haystack)
