# app/services/verdict_service.py
"""
VerdictService (gap-closing plan Stage 4) -- synthesizes the report's
verdict (build / reshape / walk_away) AFTER all sections are already
written and persisted, so it reads the finished report rather than raw
evidence, and can never contradict the body it sits on top of.

Structure mirrors section_writer_service.py deliberately: build context ->
generate draft -> validate -> one repair retry on ValueError -> persist.
The validator here is narrower than the section writer's, though -- it
checks markers are real and the schema is well-formed, the same way
validate_section_draft does, but does NOT try to mechanically verify
"genuinely persuasive" or "no confident filler". Those are judgment calls
the prompt's guardrails carry; validation here only catches what can
actually be checked structurally, same division of labor as the section
writer's validator.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.llm.json_parse import parse_json_object
from app.llm.prompts import VERDICT_PROMPT
from app.services.astra_evidence_repository import AstraEvidenceRepository
from app.services.evidence_bundle_service import EvidenceBundleService
from app.utils.clarification_schema import writer_view

logger = logging.getLogger(__name__)

VALID_VERDICTS = {"build", "reshape", "walk_away"}
VALID_CONFIDENCE = {"high", "medium", "low"}
REQUIRED_PROSE_FIELDS = (
    "holding",
    "case_for_prose",
    "case_against_prose",
    "which_won",
    "flip_condition",
)


class VerdictService:
    def __init__(
        self,
        db: Session,
        astra_repository: AstraEvidenceRepository | None = None,
    ) -> None:
        self.db = db
        self.astra_repository = astra_repository or AstraEvidenceRepository()

    def build_verdict_context(self, report_id: str) -> dict[str, Any]:
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

        sections_view: list[dict[str, Any]] = []
        # marker -> {source_id, url, domain, stance, quote} -- every marker
        # the verdict is allowed to cite, drawn from what the sections
        # actually cited (not re-ranked evidence), since the verdict must
        # never introduce a source no finished section already used.
        marker_map: dict[str, dict[str, Any]] = {}

        for section in sections:
            chunks = (
                self.db.query(models.Chunk)
                .filter_by(section_id=section.id)
                .order_by(models.Chunk.chunk_index.asc())
                .all()
            )
            if not chunks:
                # Section writer failed for this one (gap-closing plan
                # Stage 1 / partial-report survival) -- synthesize the
                # verdict from whichever sections did succeed rather than
                # losing it entirely. Only fatal if NO section has chunks
                # (checked after the loop).
                logger.info(
                    "[VERDICT] Skipping chunk-less section_id=%s report_id=%s",
                    section.id,
                    report_id,
                )
                continue

            chunk_texts = []
            for chunk in chunks:
                chunk_texts.append(chunk.chunk_text)
                for citation in chunk.citations:
                    if citation.citation_marker in marker_map:
                        continue
                    source = citation.source
                    marker_map[citation.citation_marker] = {
                        "source_id": source.id if source else None,
                        "url": source.url if source else None,
                        "domain": source.domain if source else None,
                        "stance": source.stance if source else "neutral",
                        "quote": citation.quote,
                    }

            sections_view.append(
                {"title": section.title, "text": "\n\n".join(chunk_texts)}
            )

        if not sections_view:
            raise ValueError("No section has chunks")

        # Reused, not re-derived: the same computation the gaps section and
        # the (Stage 5) PDF's "Open Questions" block use, so the verdict's
        # "no confident filler" guardrail reasons about the same gaps the
        # reader will actually see, not the LLM's own re-guess at what's
        # missing.
        unresolved_gaps = EvidenceBundleService(
            self.db, astra_repository=self.astra_repository
        ).unresolved_directives(report_id, session.clarified_summary)

        return {
            "report": {
                "id": report.id,
                "topic": report.topic,
                "clarified_summary": writer_view(session.clarified_summary),
            },
            "sections": sections_view,
            "marker_map": marker_map,
            "unresolved_gaps": unresolved_gaps,
        }

    def generate_verdict_draft(
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
                "Regenerate the full JSON so the verdict is valid."
            )

        raw_output = generate_chat(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2,
            task="verdict",
        )
        return self._parse_json(raw_output)

    def validate_verdict_draft(
        self,
        draft: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        verdict = draft.get("verdict")
        if verdict not in VALID_VERDICTS:
            raise ValueError("Verdict draft has an invalid or missing 'verdict' value")

        confidence = draft.get("confidence")
        if confidence not in VALID_CONFIDENCE:
            raise ValueError("Verdict draft has an invalid or missing 'confidence' value")

        for field in REQUIRED_PROSE_FIELDS:
            value = draft.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Verdict draft missing prose field '{field}'")

        allowed_markers = set(context["marker_map"])
        prose_text = " ".join(draft[field] for field in REQUIRED_PROSE_FIELDS)
        used_markers = set(re.findall(r"\[(CIT-\d{3})\]", prose_text))
        if not used_markers.issubset(allowed_markers):
            raise ValueError(
                "Verdict references citation marker(s) not present in any finished section"
            )

        # A confidence of "high" claiming an evidence base the sections
        # never established would be exactly the "confident filler" the
        # prompt's guardrail exists to prevent -- if literally no markers
        # were cited at all, the model ignored the grounding rules outright
        # rather than legitimately abstaining (that path still cites
        # something and says so in prose; it doesn't cite nothing).
        if not used_markers:
            raise ValueError("Verdict cites no evidence markers at all")

    def persist_verdict(self, report_id: str, draft: dict[str, Any]) -> None:
        report = self.db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        report.verdict = draft["verdict"]
        report.verdict_holding = draft["holding"]
        report.verdict_payload = json.dumps(draft)
        report.flip_condition = draft["flip_condition"]
        report.verdict_confidence = draft["confidence"]
        self.db.commit()

    def _build_prompt(self, context: dict[str, Any]) -> str:
        sections_text = "\n\n".join(
            f"### {section['title']}\n{section['text']}"
            for section in context["sections"]
        )

        marker_blocks = []
        for marker, item in context["marker_map"].items():
            marker_blocks.append(
                "\n".join(
                    [
                        f"[{marker}]",
                        f"source_id: {item.get('source_id')}",
                        f"stance: {item.get('stance')}",
                        f"domain: {item.get('domain')}",
                        f"url: {item.get('url')}",
                        f"quote: {item.get('quote')}",
                    ]
                )
            )

        return (
            VERDICT_PROMPT.replace(
                "{{REPORT_CONTEXT}}",
                json.dumps(context["report"], indent=2),
            )
            .replace("{{SECTIONS}}", sections_text)
            .replace("{{EVIDENCE_MARKERS}}", "\n\n".join(marker_blocks))
            .replace(
                "{{UNRESOLVED_GAPS}}",
                json.dumps(context.get("unresolved_gaps") or [], indent=2),
            )
        )

    def _parse_json(self, raw_output: str) -> dict[str, Any]:
        return parse_json_object(raw_output, label="Verdict")
