from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import models
from app.db.session import get_db
from app.services.orchestrator_service import OrchestratorService
from app.utils.auth_dep import current_user_id
from app.utils.rate_limit import enforce_global_daily_cap, limiter
from app.utils.sanitize import sanitize_text
from app.utils.state_machine import SessionState

router = APIRouter(tags=["Orchestrator"])


# ------------------------------------------------------------------
# Request models (JSON bodies — B1.2)
# ------------------------------------------------------------------
class StartSessionRequest(BaseModel):
    idea_description: str = Field(min_length=3, max_length=settings.MAX_TEXT_LENGTH)


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=settings.MAX_TEXT_LENGTH)


class ConsentRequest(BaseModel):
    session_id: str


def _owned_session(db: Session, session_id: str, user_id: str) -> models.Session:
    """Load a session owned by the caller, else 404 (never leak existence)."""
    session = (
        db.query(models.Session)
        .filter_by(id=session_id, user_id=user_id)
        .first()
    )
    if not session:
        raise HTTPException(404, "Session not found")
    return session


# ------------------------------------------------------------------
# 1. Start Session
# ------------------------------------------------------------------
@router.post("/start-session")
@limiter.limit(settings.START_SESSION_RATE)
def start_session(
    request: Request,
    body: StartSessionRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(current_user_id),
):
    enforce_global_daily_cap()

    session, report = OrchestratorService.start_session(
        db=db,
        user_id=user_id,
        idea_description=sanitize_text(body.idea_description),
    )

    OrchestratorService.start_clarification(db, session)

    return {
        "session_id": session.id,
        "report_id": report.id,
        "status": session.status,
        "message": "Session created. Clarification started.",
    }


# ------------------------------------------------------------------
# 2. Clarification Chat
# ------------------------------------------------------------------
@router.post("/clarification/chat")
@limiter.limit(settings.CLARIFICATION_CHAT_RATE)
def clarification_chat(
    request: Request,
    body: ChatRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(current_user_id),
):
    session = _owned_session(db, body.session_id, user_id)

    if session.status != SessionState.CLARIFYING:
        raise HTTPException(
            400,
            f"Session not in clarification state (current: {session.status})",
        )

    OrchestratorService.handle_user_message(
        db=db,
        session=session,
        message=sanitize_text(body.message),
    )

    return {
        "session_id": session.id,
        "status": session.status,
    }


# ------------------------------------------------------------------
# 3. Accept Clarification (Consent)
# ------------------------------------------------------------------
@router.post("/clarification/accept-consent")
def accept_clarification_consent(
    body: ConsentRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(current_user_id),
):
    session = _owned_session(db, body.session_id, user_id)

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
# 4. Status
# ------------------------------------------------------------------
@router.get("/status/{session_id}")
def get_status(
    session_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(current_user_id),
):
    session = _owned_session(db, session_id, user_id)

    report = (
        db.query(models.Report)
        .filter_by(session_id=session.id)
        .first()
    )

    return {
        "session_id": session.id,
        "status": session.status,
        "idea_description": session.idea_description,
        "clarified_summary": session.clarified_summary,
        "report_id": report.id if report else None,
        "report_status": report.status if report else None,
    }
