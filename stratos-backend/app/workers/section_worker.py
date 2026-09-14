from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.llm.repair import generate_with_repair
from app.services.section_writer_service import SectionWriterService
from app.utils.redis_pub import publish_event
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@celery_app.task(bind=True)
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

        # Fix-audit Part 2: shared retry-and-repair-temperature orchestration
        # (see app/llm/repair.py) -- one generate+validate pass, and on a
        # ValueError/RuntimeError exactly one more attempt with the failure
        # reason fed back and temperature raised, so the retry samples a
        # genuinely different draft instead of a near-replay.
        draft = generate_with_repair(
            generate=lambda repair_reason, temperature: service.generate_section_draft(
                context, repair_reason=repair_reason, temperature=temperature
            ),
            validate=lambda draft: service.validate_section_draft(draft, context),
            on_repair=lambda reason: logger.info(
                "[SECTION] Repairing failed draft report_id=%s section_id=%s reason=%s",
                report_id,
                section_id,
                reason,
            ),
        )

        # Fix-audit Part 1: topical-alignment findings are a quality signal,
        # never a reason to fail the section (validate_section_draft above
        # covers every correctness invariant already). Log-only for now --
        # promoting this to a section_quality_flagged SSE event is a
        # deliberate follow-up gated behind the stratos-contract-guard
        # skill, not bundled into this fix.
        quality_findings = service.assess_section_quality(draft, context)
        if quality_findings:
            logger.info(
                "[SECTION] Quality findings report_id=%s section_id=%s findings=%s",
                report_id,
                section_id,
                quality_findings,
            )

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
