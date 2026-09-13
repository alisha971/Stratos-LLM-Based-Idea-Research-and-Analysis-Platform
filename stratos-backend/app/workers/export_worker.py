from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.config import settings
from app.db import models
from app.db.session import SessionLocal
from app.utils.redis_pub import publish_event
from app.utils.state_machine import SessionState
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Matches the assembler's own inline marker format (see
# section_writer_service.py / verdict_service.py, both cite "[CIT-001]").
_MARKER_RE = re.compile(r"\[CIT-\d{3}\]")
_LINK_COLOR = "#245c3d"  # the existing brand moss green, not default blue


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def run_export(self, report_id: str, file_type: str = "pdf"):
    if file_type != "pdf":
        raise ValueError("Only PDF export is supported for MVP")

    db = SessionLocal()

    try:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        # Stage 5a: consume the assembler's own draft instead of
        # re-querying Postgres and rebuilding the same content a second
        # time. This is also the ONLY reason unresolved_gaps and the
        # verdict ever reached the PDF -- the assembler already computed
        # both and wrote them here; the old _render_pdf just never opened
        # the file.
        draft_path = _draft_path(report_id)
        if not draft_path.exists():
            raise ValueError(
                f"Assembler draft not found at {draft_path} -- run_assembler "
                "must complete before run_export"
            )
        draft = json.loads(draft_path.read_text(encoding="utf-8"))

        output_path = Path(settings.EXPORT_DIR) / f"{report_id}.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        _render_pdf(output_path, draft)

        export_record = models.ExportRecord(
            report_id=report_id,
            file_type="pdf",
            file_url=str(output_path),
        )
        db.add(export_record)
        report.status = SessionState.EXPORTED.value

        # Previously only report.status reached EXPORTED -- the session sat
        # at READY_FOR_EXPORT forever, indistinguishable from "still
        # exporting" to anything reading session state.
        session = (
            db.query(models.Session).filter_by(id=report.session_id).first()
        )
        if session:
            session.status = SessionState.EXPORTED.value

        db.commit()
        db.refresh(export_record)

        publish_event(
            "export_done",
            {
                "report_id": report_id,
                "export_id": export_record.id,
                "file_type": "pdf",
                "file_url": str(output_path),
            },
        )

    except Exception as exc:
        publish_event(
            "export_failed",
            {
                "report_id": report_id,
                "error": str(exc),
            },
        )
        raise
    finally:
        db.close()


def _draft_path(report_id: str) -> Path:
    return Path(settings.EXPORT_DIR) / f"{report_id}.json"


def _render_pdf(output_path: Path, draft: dict) -> None:
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    doc.build(_build_story(draft))


def _build_story(draft: dict) -> list:
    """Split out from _render_pdf so tests can inspect exactly what would
    be written -- each flowable's .text -- without parsing real PDF bytes
    back out."""
    styles = getSampleStyleSheet()
    sources = draft.get("sources") or {}

    story = [
        Paragraph(escape(draft.get("topic") or "Stratos Research Report"), styles["Title"]),
        Spacer(1, 20),
    ]

    verdict = draft.get("verdict")
    if verdict:
        # The verdict opens the document, before section one -- it's the
        # headline, not an appendix (Stage 5a).
        story.extend(_render_verdict(verdict, sources, styles))

    for section in draft.get("sections", []):
        story.append(Paragraph(escape(section["title"]), styles["Heading2"]))
        for chunk in section.get("chunks", []):
            story.append(
                Paragraph(_linkify(chunk.get("text") or "", sources), styles["BodyText"])
            )
            story.append(Spacer(1, 8))

        coverage_note = section.get("coverage_note")
        if coverage_note:
            story.append(Paragraph(escape(coverage_note), styles["Italic"]))
            story.append(Spacer(1, 8))

        story.append(Spacer(1, 14))

    unresolved_gaps = draft.get("unresolved_gaps") or []
    if unresolved_gaps:
        story.append(Paragraph("What We Couldn't Settle", styles["Heading2"]))
        for gap in unresolved_gaps:
            story.append(Paragraph(f"• {escape(gap)}", styles["BodyText"]))
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 14))

    if sources:
        story.append(Paragraph("Sources", styles["Heading2"]))
        for marker in sorted(sources):
            story.append(_render_source_line(marker, sources[marker], styles))
            story.append(Spacer(1, 4))

    return story


def _render_verdict(verdict: dict, sources: dict, styles) -> list:
    payload = verdict.get("payload") or {}
    blocks = [
        Paragraph("The Verdict", styles["Heading1"]),
        Paragraph(escape(verdict.get("holding") or ""), styles["Heading3"]),
        Spacer(1, 10),
    ]

    case_for = payload.get("case_for_prose")
    if case_for:
        blocks.append(Paragraph("The Case For", styles["Heading3"]))
        blocks.append(Paragraph(_linkify(case_for, sources), styles["BodyText"]))
        blocks.append(Spacer(1, 8))

    case_against = payload.get("case_against_prose")
    if case_against:
        blocks.append(Paragraph("The Case Against", styles["Heading3"]))
        blocks.append(Paragraph(_linkify(case_against, sources), styles["BodyText"]))
        blocks.append(Spacer(1, 8))

    which_won = payload.get("which_won")
    if which_won:
        blocks.append(Paragraph("Why One Side Won", styles["Heading3"]))
        blocks.append(Paragraph(_linkify(which_won, sources), styles["BodyText"]))
        blocks.append(Spacer(1, 8))

    flip_condition = verdict.get("flip_condition")
    if flip_condition:
        blocks.append(Paragraph("What Would Flip It", styles["Heading3"]))
        blocks.append(Paragraph(escape(flip_condition), styles["BodyText"]))
        blocks.append(Spacer(1, 8))

    confidence = verdict.get("confidence")
    if confidence:
        blocks.append(Paragraph(escape(f"Confidence: {confidence}"), styles["Italic"]))

    blocks.append(Spacer(1, 22))
    return blocks


def _render_source_line(marker: str, info: dict, styles) -> Paragraph:
    url = info.get("url")
    domain = info.get("domain") or url or "unknown source"
    stance = info.get("stance") or "neutral"

    if url:
        link = f'<a href="{escape(url)}" color="{_LINK_COLOR}"><u>{escape(domain)}</u></a>'
    else:
        link = escape(domain)

    return Paragraph(f"[{marker}] {link} — {escape(stance)}", styles["Normal"])


def _linkify(text: str, sources: dict) -> str:
    """Escape the raw text FIRST, then inject ReportLab's own `<a href>`
    markup for each [CIT-001] marker -- escaping after injection would
    mangle the markup itself. A marker with no resolvable URL (source_id
    was null, or nothing matched) is left as plain escaped text, not
    dropped -- the citation still reads, it just isn't clickable."""
    escaped = escape(text or "")

    def _replace(match: re.Match) -> str:
        marker = match.group(0)[1:-1]  # strip [ and ]
        info = sources.get(marker)
        url = info.get("url") if info else None
        if not url:
            return match.group(0)
        return f'<a href="{escape(url)}" color="{_LINK_COLOR}"><u>{match.group(0)}</u></a>'

    return _MARKER_RE.sub(_replace, escaped)
