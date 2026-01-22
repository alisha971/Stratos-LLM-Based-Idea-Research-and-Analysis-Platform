# app/services/orchestrator_service.py

from sqlalchemy.orm import Session
from fastapi import HTTPException
import uuid, json

from app.db import models
from app.utils.state_machine import SessionState
from app.utils.redis_pub import publish_event
from app.workers.clarification_worker import run_clarification
from app.workers.outline_worker import run_outline
from app.workers.research_worker import run_research
# from app.workers.trend_worker import run_trend
# from app.workers.competitor_worker import run_competitor


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
    def handle_clarification_ready(
        db: Session,
        session_id: str,
        payload: dict,
    ):
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session or session.status != SessionState.CLARIFYING:
            return

        session.status = SessionState.AWAITING_CONSENT
        session.clarified_summary = json.dumps({
            "final_schema": payload["schema"],
            "hard_constraints": payload.get("hard_constraints", []),
            "hypotheses": payload.get("hypotheses", []),
            "knowledge_gaps": payload.get("knowledge_gaps", []),
            "research_directives": payload.get("research_directives", []),
            "unknown_detected": payload.get("unknown_detected", []),
            "confidence_score": payload["confidence_score"],
        }, indent=2)

        db.commit()

        publish_event(
            "clarification_consent_requested",
            {
                "session_id": session.id,
                "summary": session.clarified_summary,
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
        
        report = (
            db.query(models.Report)
            .filter_by(session_id=session.id)
            .first()
        )

        publish_event(
            "clarification_completed",
            {
                "session_id": session.id,
                "state": session.status,
                "schema": session.clarified_summary,
            }
        )

        # 🔥 Trigger outline
        run_outline.delay(report.id)    
        
        
    @staticmethod
    def handle_outline_ready(
        db: Session,
        report_id: str,
        sections: list,
    ):
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            return

        session = (
            db.query(models.Session)
            .filter_by(id=report.session_id)
            .first()
        )
        if not session:
            return

        # 🔒 Idempotency guard
        if session.status != SessionState.READY_FOR_RESEARCH:
            return

        # -----------------------------
        # State transition - Accept Outline
        # -----------------------------
        session.status = SessionState.OUTLINE_GENERATED
        report.status = SessionState.OUTLINE_GENERATED
        db.commit()

        publish_event(
            "outline_accepted",
            {
                "session_id": session.id,
                "report_id": report.id,
                "sections": sections,
            }
        )

        # -----------------------------
        # FAN-OUT (parallel)
        # -----------------------------
        session.status = SessionState.RESEARCH_RUNNING
        report.status = SessionState.RESEARCH_RUNNING
        db.commit()

        publish_event(
            "research_started",
            {
                "session_id": session.id,
                "report_id": report.id,
            }
        )

        run_research.delay(report.id)
        # run_trend.delay(report.id)
        # run_competitor.delay(report.id)