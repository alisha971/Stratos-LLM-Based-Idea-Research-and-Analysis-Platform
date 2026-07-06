from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.services.section_writer_service import SectionWriterService
from app.utils.redis_pub import publish_event
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def run_section_writer(self, report_id: str, section_id: str):
    db = SessionLocal()

    try:
        publish_event(
            "section_started",
            {
                "report_id": report_id,
                "section_id": section_id,
            },
        )

        service = SectionWriterService(db=db)
        context = service.build_section_context(report_id, section_id)

        draft = service.generate_section_draft(context)
        try:
            service.validate_section_draft(draft, context)
        except ValueError as exc:
            logger.info(
                "[SECTION] Repairing invalid draft report_id=%s section_id=%s reason=%s",
                report_id,
                section_id,
                exc,
            )
            draft = service.generate_section_draft(context, repair_reason=str(exc))
            service.validate_section_draft(draft, context)

        chunk_ids = service.persist_section_chunks(
            report_id=report_id,
            section_id=section_id,
            chunks=draft["chunks"],
            citation_map=context["citation_map"],
        )

        for chunk_id, chunk in zip(chunk_ids, draft["chunks"], strict=True):
            citations = [
                {
                    **citation,
                    "astra_evidence_id": context["citation_map"]
                    .get(citation.get("marker"), {})
                    .get("astra_evidence_id"),
                }
                for citation in chunk.get("citations", [])
            ]
            publish_event(
                "section_chunk",
                {
                    "report_id": report_id,
                    "section_id": section_id,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk["chunk_index"],
                    "text": chunk["text"],
                    "citations": citations,
                    "source_mode": context["source_mode"],
                },
            )

        if chunk_ids:
            celery_app.send_task(
                "app.workers.embedding_worker.run_embedding",
                args=[report_id, chunk_ids],
            )

        publish_event(
            "section_done",
            {
                "report_id": report_id,
                "section_id": section_id,
                "chunk_count": len(chunk_ids),
            },
        )

    except Exception as exc:
        publish_event(
            "section_failed",
            {
                "report_id": report_id,
                "section_id": section_id,
                "error": str(exc),
            },
        )
        raise

    finally:
        db.close()
