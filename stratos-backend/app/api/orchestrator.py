from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.orchestrator_service import OrchestratorService
from app.db import models

router = APIRouter()


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

    questions = OrchestratorService.start_clarification(db, session)

    return {
        "session_id": session.id,
        "report_id": report.id,
        "clarifying_questions": questions
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
