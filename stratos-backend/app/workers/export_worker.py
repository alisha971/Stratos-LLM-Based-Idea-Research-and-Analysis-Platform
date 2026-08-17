from __future__ import annotations

import logging
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

        output_path = Path(settings.EXPORT_DIR) / f"{report_id}.pdf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sections = (
            db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )
        if not sections:
            raise ValueError("No sections found")

        _render_pdf(output_path, report, sections)

        export_record = models.ExportRecord(
            report_id=report_id,
            file_type="pdf",
            file_url=str(output_path),
        )
        db.add(export_record)
        report.status = SessionState.EXPORTED.value
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


def _render_pdf(output_path: Path, report: models.Report, sections: list[models.Section]) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)

    story = [
        Paragraph("Stratos Research Report", styles["Title"]),
        Spacer(1, 16),
        Paragraph(f"Report ID: {escape(report.id)}", styles["Normal"]),
        Spacer(1, 24),
    ]

    for section in sections:
        story.append(Paragraph(escape(section.title), styles["Heading2"]))
        chunks = sorted(section.chunks, key=lambda chunk: chunk.chunk_index or 0)
        for chunk in chunks:
            story.append(Paragraph(escape(chunk.chunk_text), styles["BodyText"]))
            if chunk.citations:
                markers = ", ".join(
                    sorted(
                        citation.citation_marker
                        for citation in chunk.citations
                        if citation.citation_marker
                    )
                )
                if markers:
                    story.append(
                        Paragraph(
                            escape(f"Citations: {markers}"),
                            styles["Italic"],
                        )
                    )
            story.append(Spacer(1, 8))

        story.append(Spacer(1, 14))

    doc.build(story)
