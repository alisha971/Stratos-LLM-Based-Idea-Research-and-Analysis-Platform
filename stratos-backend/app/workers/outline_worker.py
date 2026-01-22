from sqlalchemy.orm import Session
import json, re

from app.workers.celery_app import celery_app
from app.db.session import SessionLocal
from app.db import models
from app.llm.client import generate_chat
from app.llm.prompts import OUTLINE_PROMPT
from app.utils.redis_pub import publish_event

CORE_SECTIONS = [
    "Problem Context & Validation",
    "Target Users & Personas",
    "Existing Solutions",
    "Competitor Landscape",
    "Market & Industry Trends",
    "Opportunities & Gaps",
    "Risks & Open Questions",
]

ALLOWED_OPTIONAL_SECTIONS = {
    "Technical Feasibility",
    "Regulatory Considerations",
    "Go-To-Market Strategy",
}

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def run_outline(self, report_id: str):
    """
    TODO:
    1. Load report
    2. Load session.clarified_summary
    3. Validate clarified_summary exists
    4. Call LLM to generate outline
    5. Parse + normalize section titles
    6. Delete existing sections (idempotent)
    7. Insert ordered sections
    8. Publish outline_ready SSE event
    """
    db: Session = SessionLocal()

    try:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        session = db.query(models.Session).filter_by(id=report.session_id).first()
        if not session or not session.clarified_summary:
            raise ValueError("Clarified summary missing")

        # -------------------------------
        # Call LLM
        # -------------------------------
        prompt = OUTLINE_PROMPT.replace(
            "{{CLARIFIED_SUMMARY}}",
            session.clarified_summary
        )

        raw_output = generate_chat(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2,
        )

        section_titles = parse_outline(raw_output)

        # -------------------------------
        # Idempotent persistence
        # -------------------------------
        db.query(models.Section).filter_by(report_id=report_id).delete()

        sections = []
        for idx, title in enumerate(section_titles, start=1):
            section = models.Section(
                report_id=report_id,
                title=title,
                order_index=idx,
            )
            db.add(section)
            sections.append({
                "section_id": section.id,
                "title": title,
                "order_index": idx,
            })
            
        db.commit()

        # -------------------------------
        # Emit event
        # -------------------------------
        publish_event(
            "outline_ready",
            {
                "report_id": report_id,
                "sections": sections,
            }
        )

    finally:
        db.close()

    
    
# LLM OUTPUT (UNTRUSTED) -> PARSING    
def parse_outline(raw_output: str) -> list[str]:
    """
    Parse STRICT JSON output from LLM.
    Enforce core sections + limit optional sections.
    """
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        raise ValueError("Outline LLM output is not valid JSON")

    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Missing or invalid 'sections' array")

    cleaned = []
    seen = set()

    # Enforce core sections first (deterministic)
    for core in CORE_SECTIONS:
        cleaned.append(core)
        seen.add(core.lower())

    # Add optional sections from LLM output
    for title in sections:
        if not isinstance(title, str):
            continue

        key = title.strip().lower()
        if key in seen:
            continue

        if title in ALLOWED_OPTIONAL_SECTIONS:
            cleaned.append(title)
            seen.add(key)

        if len(cleaned) >= len(CORE_SECTIONS) + 3:
            break

    return cleaned
