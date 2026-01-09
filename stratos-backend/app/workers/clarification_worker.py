# app/workers/clarification_worker.py

import json, re
import uuid
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.llm.client import generate_chat
from app.llm.prompts import CLARIFICATION_CONTROLLER_PROMPT
from app.db.session import SessionLocal
from app.db import models
from app.utils.redis_pub import publish_event

CONFIDENCE_THRESHOLD = 0.95

SCHEMA_FIELDS = [
    "project_domain",
    "target_persona",
    "core_problem",
    "current_workaround",
    "proposed_solution",
    "differentiation",
]


def merge_schema(existing: dict, incoming: dict) -> dict:
    merged = existing.copy()

    for key in SCHEMA_FIELDS:
        if merged.get(key) not in (None, "", []):
            # Field already known → do NOT overwrite
            continue

        incoming_value = incoming.get(key)
        if incoming_value not in (None, "", []):
            merged[key] = incoming_value

    return merged

def compute_confidence(schema: dict) -> float:
    """
    Deterministic confidence based on schema completeness.
    Monotonic by design.
    """
    filled = sum(
        1 for v in schema.values()
        if v not in (None, "", [])
    )
    return round(filled / len(SCHEMA_FIELDS), 2)

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def run_clarification(self, session_id: str):
    """
    Stateless clarification intelligence.
    Reads conversation, asks next question, emits update.
    """
    db: Session = SessionLocal()

    try:
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session:
            return

        # Load full conversation
        chat_messages = (
            db.query(models.ChatMessage)
            .filter_by(session_id=session_id)
            .order_by(models.ChatMessage.created_at.asc())
            .all()
        )

        messages = [
            {"role": "system", "content": CLARIFICATION_CONTROLLER_PROMPT}
        ]

        for msg in chat_messages:
            messages.append({
                "role": msg.role,
                "content": msg.message,
            })

        raw_output = generate_chat(
            messages=messages,
            temperature=0.2,
        )

        raw_output = raw_output.strip()

        # Guard 1: empty response
        if not raw_output:
            raise ValueError("LLM returned empty response")

        # Guard 2: extract JSON object if extra text exists
        try:
            result = json.loads(raw_output)
        except json.JSONDecodeError:
            # Attempt to extract JSON block
            match = re.search(r"\{.*\}", raw_output, re.DOTALL)
            if not match:
                raise ValueError(f"Invalid JSON from LLM: {raw_output[:300]}")
            result = json.loads(match.group(0))

        # -------------------------------
        # Merge schema (MVP accumulation)
        # -------------------------------
        existing_schema = session.clarification_schema or {}
        incoming_schema = result.get("updated_schema") or {}

        merged_schema = merge_schema(existing_schema, incoming_schema)
        session.clarification_schema = merged_schema

        # -------------------------------
        # Calculate confidence (NEW)
        # -------------------------------
        confidence_score = compute_confidence(merged_schema)

        # -------------------------------
        # Persist assistant message (JSON ONLY)
        # -------------------------------

        # Build assistant conversational text
        db.add(models.ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="assistant",
            message=json.dumps({
                "mirror_summary": result.get("mirror_summary"),
                "next_question": result.get("next_question"),
            }),
        ))
        db.commit()

        # Emit conversational update (UI + orchestrator listening)
        publish_event(
            "clarification_update",
            {
                "session_id": session_id,
                "schema": merged_schema,
                "hard_constraints": result.get("hard_constraints"),
                "hypotheses": result.get("hypotheses"),
                "knowledge_gaps": result.get("knowledge_gaps"),
                "research_directives": result.get("research_directives"),
                "confidence_score": confidence_score,
                "unknown_detected": result.get("unknown_detected"),
                "turn_fatigue": result.get("turn_fatigue"),
                "mirror_summary": result.get("mirror_summary"),
                "next_question": result.get("next_question"),
            }
        )
        
        # 🔔 Deterministic stop signal
        if confidence_score >= CONFIDENCE_THRESHOLD:
            publish_event(
                "clarification_ready",
                {
                    "session_id": session_id,
                    "schema": merged_schema,
                    "hard_constraints": result.get("hard_constraints", []),
                    "hypotheses": result.get("hypotheses", []),
                    "knowledge_gaps": result.get("knowledge_gaps", []),
                    "research_directives": result.get("research_directives", []),
                    "unknown_detected": result.get("unknown_detected", []),
                    "confidence_score": confidence_score,
                    
                    
                }
            )

    finally:
        db.close()
