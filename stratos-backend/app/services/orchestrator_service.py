from sqlalchemy.orm import Session
from app.db import models
from app.utils.state_machine import SessionState
from app.utils.redis_pub import publish_event
import uuid


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
        session.status = SessionState.CLARIFYING
        db.commit()

        publish_event("clarification_started", {
            "session_id": session.id,
            "state": SessionState.CLARIFYING
        })

        # mocked clarifying questions for now
        questions = [
            "Who is the target user?",
            "What problem are you trying to solve?",
            "Is this B2B or B2C?"
        ]

        return questions

    @staticmethod
    def submit_clarification(db: Session, session: models.Session, summary: str):
        session.clarified_summary = summary
        session.status = SessionState.READY_FOR_RESEARCH
        db.commit()

        publish_event("clarification_completed", {
            "session_id": session.id,
            "state": SessionState.READY_FOR_RESEARCH
        })
