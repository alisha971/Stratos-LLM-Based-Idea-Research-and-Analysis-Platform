from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import models
from app.db.session import get_db
from app.services.orchestrator_service import OrchestratorService
from app.utils.auth_dep import current_user_id

router = APIRouter(tags=["Reports"])


def _owned_report(db: Session, report_id: str, user_id: str) -> models.Report:
    report = (
        db.query(models.Report)
        .join(models.Session, models.Report.session_id == models.Session.id)
        .filter(models.Report.id == report_id, models.Session.user_id == user_id)
        .first()
    )
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/reports")
def list_reports(
    db: Session = Depends(get_db),
    user_id: str = Depends(current_user_id),
):
    return {"reports": OrchestratorService.list_reports(db, user_id)}


@router.get("/reports/{report_id}")
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(current_user_id),
):
    _owned_report(db, report_id, user_id)
    return OrchestratorService.get_report_view(db, report_id)


@router.get("/exports/{report_id}/file")
def get_export_file(
    report_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(current_user_id),
):
    _owned_report(db, report_id, user_id)

    export = (
        db.query(models.ExportRecord)
        .filter_by(report_id=report_id)
        .order_by(models.ExportRecord.created_at.desc())
        .first()
    )
    if not export or not export.file_url:
        raise HTTPException(404, "No export available for this report yet")

    if settings.EXPORT_STORAGE == "r2":
        # Premium path (B6): file_url holds the object key; redirect to presigned URL.
        from app.utils.storage import presigned_url

        return RedirectResponse(url=presigned_url(export.file_url), status_code=302)

    path = Path(export.file_url)
    if not path.exists():
        raise HTTPException(404, "Export file missing on disk")

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename="stratos-report.pdf",
    )
