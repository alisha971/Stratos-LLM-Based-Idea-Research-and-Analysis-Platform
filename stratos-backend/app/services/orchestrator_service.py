# app/services/orchestrator_service.py

from sqlalchemy.orm import Session
from fastapi import HTTPException
import uuid, json

from app.db import models
from app.utils.state_machine import SessionState
from app.utils.redis_pub import publish_event
from app.workers.clarification_worker import run_clarification


class OrchestratorService:
    """
    SINGLE source of truth for session state.
    Orchestrates conversation flow and transitions.
    """

    # --------------------------------------------------
    # Session bootstrap
    # --------------------------------------------------
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

        # Save first user message (context seeding)
        db.add(models.ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role="user",
            message=idea_description,
        ))

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
            "state": session.status,
        })

        return session, report

    # --------------------------------------------------
    # Start clarification conversation
    # --------------------------------------------------
    @staticmethod
    def start_clarification(db: Session, session: models.Session):
        if session.status != SessionState.CREATED:
            raise HTTPException(400, "Invalid state")

        session.status = SessionState.CLARIFYING
        db.commit()

        publish_event("clarification_started", {
            "session_id": session.id
        })

        run_clarification.delay(session.id)

    # --------------------------------------------------
    # Handle user message during clarification
    # --------------------------------------------------
    @staticmethod
    def handle_user_message(db: Session, session: models.Session, message: str):
        if session.status not in (
            SessionState.CLARIFYING,
            SessionState.AWAITING_CONSENT,
        ):
            raise HTTPException(400, "Clarification not active")

        db.add(models.ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role="user",
            message=message,
        ))
        db.commit()

        # Resume clarification intelligence
        run_clarification.delay(session.id)

    # --------------------------------------------------
    # Transition to consent (no hard logic yet)
    # --------------------------------------------------
    @staticmethod
    def request_consent(
        db: Session,
        session: models.Session,
        clarification_result: dict,
    ):
        """
        Persist the proposed clarification summary and research plan.
        """

        session.clarified_summary = json.dumps(clarification_result, indent=2)
        session.status = SessionState.AWAITING_CONSENT
        db.commit()

        publish_event(
            "clarification_consent_requested",
            {
                "session_id": session.id,
                "summary": clarification_result,
            }
        )

    # --------------------------------------------------
    # User accepts proposed research plan
    # --------------------------------------------------
    @staticmethod
    def accept_consent(db: Session, session: models.Session):
        if session.status != SessionState.AWAITING_CONSENT:
            raise HTTPException(400, "Consent not requested")

        if not session.clarified_summary:
            raise HTTPException(400, "Missing clarification summary")

        session.status = SessionState.READY_FOR_RESEARCH
        db.commit()

        publish_event(
            "clarification_completed",
            {
                "session_id": session.id,
                "state": session.status,
            }
        )
