from __future__ import annotations

import json
import logging
from pathlib import Path

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
def run_assembler(self, report_id: str):
    db = SessionLocal()

    try:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        sections = (
            db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )
        if not sections:
            raise ValueError("No sections found")

        assembled_sections = []
        chunk_count = 0
        for section in sections:
            chunks = (
                db.query(models.Chunk)
                .filter_by(section_id=section.id)
                .order_by(models.Chunk.chunk_index.asc())
                .all()
            )
            if not chunks:
                raise ValueError(f"Missing chunks for section_id={section.id}")

            assembled_chunks = []
            for chunk in chunks:
                citations = [
                    {
                        "marker": citation.citation_marker,
                        "source_id": citation.source_id,
                        "quote": citation.quote,
                    }
                    for citation in chunk.citations
                ]
                assembled_chunks.append(
                    {
                        "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.chunk_text,
                        "citations": citations,
                    }
                )
                chunk_count += 1

            assembled_sections.append(
                {
                    "section_id": section.id,
                    "title": section.title,
                    "order_index": section.order_index,
                    "chunks": assembled_chunks,
                }
            )

        draft = {
            "report_id": report_id,
            "sections": assembled_sections,
        }
        draft_path = _draft_path(report_id)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")

        report.status = SessionState.READY_FOR_EXPORT.value
        db.commit()

        publish_event(
            "report_assembled",
            {
                "report_id": report_id,
                "section_count": len(assembled_sections),
                "chunk_count": chunk_count,
                "draft_path": str(draft_path),
            },
        )

    except Exception as exc:
        publish_event(
            "assembler_failed",
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
