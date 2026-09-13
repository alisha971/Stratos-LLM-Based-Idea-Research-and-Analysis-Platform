from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.services.verdict_service import VerdictService
from app.utils.redis_pub import publish_event
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@celery_app.task(bind=True)
def run_verdict(self, report_id: str):
    """Gap-closing plan Stage 4. Runs after sections_done, before the
    assembler. A failure here is non-fatal to the run (see
    OrchestratorService.handle_stage_failed) -- the report still assembles
    and exports without a verdict rather than losing an otherwise
    complete set of sections."""
    db = SessionLocal()

    try:
        publish_event("verdict_started", {"report_id": report_id})

        service = VerdictService(db=db)
        context = service.build_verdict_context(report_id)

        try:
            draft = service.generate_verdict_draft(context)
            service.validate_verdict_draft(draft, context)
        except (ValueError, RuntimeError) as exc:
            logger.info(
                "[VERDICT] Repairing failed draft report_id=%s reason=%s",
                report_id,
                exc,
            )
            draft = service.generate_verdict_draft(context, repair_reason=str(exc))
            service.validate_verdict_draft(draft, context)

        service.persist_verdict(report_id, draft)

        # Stage 5c/5d: full prose fields ride along in the event itself --
        # same pattern section_chunk already uses (the SSE payload carries
        # real content, not just a pointer). Without this the frontend
        # could only show the verdict after export_done, well after the
        # user finished reading the sections it was synthesized from.
        publish_event(
            "verdict_ready",
            {
                "report_id": report_id,
                "verdict": draft["verdict"],
                "holding": draft["holding"],
                "case_for_prose": draft["case_for_prose"],
                "case_against_prose": draft["case_against_prose"],
                "which_won": draft["which_won"],
                "flip_condition": draft["flip_condition"],
                "confidence": draft["confidence"],
                # Already computed for the prompt's own guardrail
                # (context["unresolved_gaps"], see build_verdict_context) --
                # riding along here too so "what we couldn't settle" can
                # render next to the verdict immediately, rather than
                # waiting for export_done to fetch the full report.
                "unresolved_gaps": context.get("unresolved_gaps") or [],
            },
        )

    except Exception as exc:
        publish_event(
            "verdict_failed",
            {
                "report_id": report_id,
                "error": str(exc),
            },
        )
        raise

    finally:
        db.close()
