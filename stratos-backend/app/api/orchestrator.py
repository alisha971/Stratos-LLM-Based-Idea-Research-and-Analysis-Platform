from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.services.orchestrator_service import OrchestratorService
from app.utils.state_machine import SessionState

router = APIRouter(prefix="/orchestrate", tags=["Orchestrator"])


# ------------------------------------------------------------------
# 1. Start Session (context seeding + first AI question)
# - Seeds context
# - Moves session → CLARIFYING
# - Triggers first clarification worker run
# ------------------------------------------------------------------
@router.post("/start-session")
def start_session(
    user_id: str,
    idea_description: str,
    db: Session = Depends(get_db),
):
    session, report = OrchestratorService.start_session(
        db=db,
        user_id=user_id,
        idea_description=idea_description,
    )

    # Start clarification immediately
    OrchestratorService.start_clarification(db, session)

    return {
        "session_id": session.id,
        "report_id": report.id,
        "status": session.status,
        "message": "Session created. Clarification started."
    }


# ------------------------------------------------------------------
# 2. Clarification Chat (multi-turn loop)
# - Accepts user replies
# - Appends message
# - Triggers clarification worker
# ------------------------------------------------------------------
@router.post("/clarification/chat")
def clarification_chat(
    session_id: str,
    message: str,
    db: Session = Depends(get_db),
):
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    if session.status != SessionState.CLARIFYING:
        raise HTTPException(
            400,
            f"Session not in clarification state (current: {session.status})"
        )

    OrchestratorService.handle_user_message(
        db=db,
        session=session,
        message=message,
    )

    return {
        "session_id": session.id,
        "status": session.status,
    }


# ------------------------------------------------------------------
# 3. Accept Clarification (Consent)
# - Called AFTER frontend receives
#   `clarification_consent_requested` SSE
# ------------------------------------------------------------------
@router.post("/clarification/accept-consent")
def accept_clarification_consent(
    session_id: str,
    db: Session = Depends(get_db),
):
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    if session.status != SessionState.AWAITING_CONSENT:
        raise HTTPException(
            400,
            f"Consent not requested (current: {session.status})",
        )

    OrchestratorService.accept_consent(db, session)

    return {
        "session_id": session.id,
        "status": session.status,
        "message": "Clarification accepted. Research can begin.",
    }


# ------------------------------------------------------------------
# 4. Status (debug + frontend sync)
# ------------------------------------------------------------------
@router.get("/status/{session_id}")
def get_status(
    session_id: str,
    db: Session = Depends(get_db),
):
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    return {
        "session_id": session.id,
        "status": session.status,
        "idea_description": session.idea_description,
        "clarified_summary": session.clarified_summary,
    }
