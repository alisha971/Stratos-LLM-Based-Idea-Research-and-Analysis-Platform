from sqlalchemy.orm import Session
from app.db import models
from app.utils.state_machine import SessionState
from app.utils.redis_pub import publish_event
import uuid
from fastapi import HTTPException
from app.workers.clarification_worker import run_clarification


class OrchestratorService:

    @staticmethod
    def start_session(db: Session, user_id: str, idea_description: str):
        session = models.Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status=SessionState.CREATED,
            idea_description=idea_description,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        report = models.Report(
            id=str(uuid.uuid4()),
            session_id=session.id,
            topic="Pending clarification",
            status=SessionState.CREATED,
        )
        db.add(report)
        db.commit()

        publish_event("session_created", {
            "session_id": session.id,
            "state": SessionState.CREATED
        })

        return session, report

    @staticmethod
    def start_clarification(db: Session, session: models.Session):
        if session.status != SessionState.CREATED:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot start clarification from state {session.status}"
            )

        session.status = SessionState.CLARIFYING
        db.commit()

        publish_event("clarification_started", {
            "session_id": session.id,
            "state": SessionState.CLARIFYING
        })

        # 🔥 Trigger Clarification Worker (async, non-blocking)
        run_clarification.delay(
            session_id=session.id,
            idea=session.idea_description
        )


    @staticmethod
    def submit_clarification(db: Session, session: models.Session, summary: str):
        if session.status != SessionState.CLARIFYING:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot submit clarification from state {session.status}"
            )

        session.clarified_summary = summary
        session.status = SessionState.READY_FOR_RESEARCH
        db.commit()

        publish_event("clarification_completed", {
            "session_id": session.id,
            "state": SessionState.READY_FOR_RESEARCH
        })

    @staticmethod
    def start_research(db: Session, session: models.Session):
        if session.status != SessionState.READY_FOR_RESEARCH:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot start research from state {session.status}"
            )

        session.status = SessionState.RESEARCH_RUNNING
        db.commit()

        publish_event("research_started", {
            "session_id": session.id,
            "state": session.status
        })

        return session

    @staticmethod
    def generate_outline(db: Session, session: models.Session):
        if session.status != SessionState.RESEARCH_RUNNING:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot generate outline from state {session.status}"
            )

        session.status = SessionState.OUTLINE_GENERATED
        db.commit()

        publish_event("outline_generated", {
            "session_id": session.id,
            "state": session.status
        })

        # Still mocked – will be worker in Phase D Part 2
        return [
            "Problem Overview",
            "Market Landscape",
            "Competitor Analysis",
            "Trends & Research",
            "Opportunities & Gaps",
            "Recommendations"
        ]
