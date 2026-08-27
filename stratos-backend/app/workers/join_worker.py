# app/workers/join_worker.py
"""
Bounded-timeout fallback for the research/trend/competitor join.

The orchestrator is purely event-driven (see redis_sub.py) -- it never polls.
So if `trend_ready` or `competitor_ready` simply never arrives (a crashed
worker, a dropped Celery message, a silent hang), nothing would ever
re-check the join. This task is scheduled once, 90s after the fan-out
dispatches all three legs (see OrchestratorService.handle_outline_ready),
and re-runs the same advance check research_join_service's event-driven
callers use -- it's what unsticks the pipeline if a leg is truly gone.

Idempotent and cheap to over-schedule: try_advance_to_writing no-ops unless
the session is still waiting on this join, so a race with the event-driven
path (the last leg arrives right as this fires) is harmless either way.
"""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def check_research_join(self, report_id: str):
    # Lazy import: orchestrator_service imports this module to schedule the
    # task, so importing it back at module load time would be a cycle.
    from app.services.orchestrator_service import OrchestratorService

    db = SessionLocal()
    try:
        OrchestratorService.try_advance_to_writing(db, report_id)
    except Exception:
        logger.exception(
            "[JOIN] check_research_join failed for report_id=%s", report_id
        )
    finally:
        db.close()
