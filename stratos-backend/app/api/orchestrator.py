from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.services.orchestrator_service import OrchestratorService

router = APIRouter(prefix="/orchestrate", tags=["Orchestrator"])


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

    # 🔥 Async clarification (worker + SSE)
    OrchestratorService.start_clarification(db, session)

    return {
        "session_id": session.id,
        "report_id": report.id,
        "status": session.status,
        "message": "Session created. Clarification started. Listen on SSE."
    }

@router.post("/submit-clarification")
def submit_clarification(
    session_id: str,
    clarified_summary: str,
    db: Session = Depends(get_db),
):
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    OrchestratorService.submit_clarification(
        db=db,
        session=session,
        summary=clarified_summary,
    )

    return {
        "session_id": session.id,
        "status": session.status
    }

@router.post("/start-research")
def start_research(
    session_id: str,
    db: Session = Depends(get_db),
):
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    OrchestratorService.start_research(db, session)

    return {
        "session_id": session.id,
        "status": session.status
    }

@router.post("/generate-outline")
def generate_outline(
    session_id: str,
    db: Session = Depends(get_db),
):
    session = db.query(models.Session).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    OrchestratorService.generate_outline(db, session)

    return {
        "session_id": session.id,
        "status": session.status
    }

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


