import json
import redis
from app.config import settings
from app.db.session import SessionLocal
from app.services.orchestrator_service import OrchestratorService

def start_event_listener():
    """
    Background Redis Pub/Sub listener.
    Listens for clarification_ready and triggers orchestrator transitions.
    """
    r = redis.Redis.from_url(settings.REDIS_PUBSUB_URL)
    pubsub = r.pubsub()
    pubsub.subscribe("stratos_events")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue

        try:
            event = json.loads(message["data"])
        except Exception:
            continue

        event_type = event.get("type")
        payload = event.get("payload", {})

        if event_type == "clarification_ready":
            db = SessionLocal()
            try:
                OrchestratorService.handle_clarification_ready(
                    db=db,
                    session_id=payload["session_id"],
                    payload=payload,
                )
            finally:
                db.close()

        elif event_type == "outline_ready":
            # orchestrator fan-out logic
            db = SessionLocal()
            try:
                OrchestratorService.handle_outline_ready(
                    db=db,
                    report_id=payload["report_id"],
                    sections=payload["sections"],
                )
            finally:
                db.close()

        elif event_type == "research_done":
            db = SessionLocal()
            try:
                OrchestratorService.handle_research_done(
                    db=db,
                    report_id=payload["report_id"],
                )
            finally:
                db.close()

        elif event_type == "trend_ready":
            # Best-effort leg of the research fan-out (see
            # research_join_service) -- section writing does not wait on
            # this alone the way it waits on research_done.
            db = SessionLocal()
            try:
                OrchestratorService.handle_trend_ready(
                    db=db,
                    report_id=payload["report_id"],
                )
            finally:
                db.close()

        elif event_type == "competitor_ready":
            db = SessionLocal()
            try:
                OrchestratorService.handle_competitor_ready(
                    db=db,
                    report_id=payload["report_id"],
                )
            finally:
                db.close()

        elif event_type == "section_done":
            db = SessionLocal()
            try:
                OrchestratorService.handle_section_done(
                    db=db,
                    report_id=payload["report_id"],
                )
            finally:
                db.close()

        elif event_type == "sections_done":
            db = SessionLocal()
            try:
                OrchestratorService.handle_sections_done(
                    db=db,
                    report_id=payload["report_id"],
                )
            finally:
                db.close()

        elif event_type == "report_assembled":
            db = SessionLocal()
            try:
                OrchestratorService.handle_report_assembled(
                    db=db,
                    report_id=payload["report_id"],
                )
            finally:
                db.close()

        # Catch-all: every event type ending in "_failed" (clarification,
        # outline, research, trend, competitor, section, section_writing,
        # assembler, export). Before this branch existed, none of these
        # drove any state change -- a failure just stalled the session
        # silently, forever. Placed last so it can never shadow one of the
        # specific branches above (none of them end in "_failed").
        elif event_type and event_type.endswith("_failed"):
            db = SessionLocal()
            try:
                OrchestratorService.handle_stage_failed(
                    db=db,
                    event_type=event_type,
                    payload=payload,
                )
            finally:
                db.close()