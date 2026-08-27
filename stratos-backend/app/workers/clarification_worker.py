# app/workers/clarification_worker.py

import json, re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.llm.client import generate_chat
from app.llm.prompts import CLARIFICATION_CONTROLLER_PROMPT
from app.db.session import SessionLocal
from app.db import models
from app.utils.clarification_schema import (
    ASKED_FIELDS_KEY,
    IDEA_CAPTURED_KEY,
    IDEA_SCHEMA_FIELDS,
    confidence_score,
    is_resolved,
    mark_unknown,
    serialize_for_downstream,
    unknown_directive,
    unresolved_fields,
)
from app.utils.redis_pub import publish_event

CONFIDENCE_THRESHOLD = 0.95

# Matches the "Maximum clarification turns: 5" rule the controller prompt
# already states. Enforcing it here is what makes it a guarantee rather than a
# request the model can ignore.
MAX_CLARIFICATION_TURNS = 5

# Floor on the other side: without this, a single rich first message lets the
# model fill most fields and flag the rest unknown in one turn, collapsing the
# whole guided conversation into a single exchange. A real design-thinking
# pass over an idea takes several back-and-forths even once the six fields are
# nominally known -- constraints and assumptions still need probing.
MIN_CLARIFICATION_TURNS = 3

# Social turns (greetings, "do you remember me?", off-topic asides) do not
# consume the MAX_CLARIFICATION_TURNS budget -- so this absolute ceiling on
# total messages is what stops unbounded chit-chat from looping forever.
# Budget math: a full substantive conversation is ~11 messages (idea + 5
# question/answer exchanges), leaving room for ~4 social exchanges on top.
MAX_TOTAL_MESSAGES = 20

# Model-declared intents that mean "this message is not about the idea".
SOCIAL_INTENTS = {"greeting", "meta_question", "off_topic"}

# Fallbacks when the model classifies a message as social but returns no
# usable social_reply. meta_question's honest no-memory answer lives in the
# prompt's IDENTITY & MEMORY rules; this is the last-resort canned version.
SOCIAL_FALLBACK_REPLIES = {
    "greeting": "Hey! I'm here to turn your idea into a researched report.",
    "meta_question": (
        "Every report session starts fresh — I don't carry over past "
        "conversations yet, but I'm keeping track of everything you share "
        "here."
    ),
    "off_topic": (
        "Happy to chat, but my job is getting your idea researched properly."
    ),
}

# Pivot used after a social reply when nothing about the idea is known yet
# (e.g. the very first message was a greeting).
IDEA_PIVOT_QUESTION = (
    "So — tell me about the idea you'd like me to research. A sentence or "
    "two is perfect."
)

CLOSING_QUESTION = (
    "I have enough to begin — I'll research the open angles and build your "
    "report. Ready to start?"
)

# Used once the six schema fields are resolved but MIN_CLARIFICATION_TURNS
# hasn't been reached yet -- keeps the remaining turns focused on the
# constraints/assumptions a design-thinking pass should still surface, rather
# than re-asking questions already answered.
DEEPENING_QUESTIONS = [
    "Are there any hard constraints I should factor in — timeline, budget, "
    "platform, or regulatory requirements?",
    "What's the riskiest assumption you're making about this idea right now?",
    "Is there anything about how {target_persona} behave today that might "
    "make this harder than it looks?",
]


def merge_schema(existing: dict, incoming: dict) -> dict:
    merged = existing.copy()

    for key in IDEA_SCHEMA_FIELDS:
        if is_resolved(merged.get(key)):
            # Field already answered, or explicitly marked unanswerable.
            # Either way it is closed — never reopen it (prompt ANTI-REGRESSION).
            continue

        incoming_value = incoming.get(key)
        if incoming_value not in (None, "", []):
            merged[key] = incoming_value

    return merged


def _unknown_target_fields(
    result: dict[str, Any],
    schema: dict[str, Any],
    asked_before: list[str],
) -> list[str]:
    """Which fields the model's ``unknown_detected`` flag refers to.

    Only ever returns a field that was actually posed as a question in a
    PRIOR turn (``asked_before``). Without this gate the model can claim a
    field is unknown before the user was ever asked about it -- exactly what
    collapsed clarification into a single exchange: it filled five fields and
    declared the sixth unknown in the same turn it first saw the idea.
    """
    gaps = result.get("knowledge_gaps")
    named: list[str] = []
    if isinstance(gaps, dict):
        named = [field for field in gaps if field in IDEA_SCHEMA_FIELDS]
    elif isinstance(gaps, list):
        named = [field for field in gaps if field in IDEA_SCHEMA_FIELDS]

    candidates = named or asked_before[-1:]

    return [
        field
        for field in candidates
        if field in asked_before and not is_resolved(schema.get(field))
    ]


def _mark_fields_unknown(
    schema: dict[str, Any],
    fields: list[str],
    llm_directives: Any,
) -> None:
    for field in fields:
        schema[field] = mark_unknown(
            field,
            unknown_directive(field, schema, llm_directives),
        )


def _deepening_question(turn_index: int, schema: dict[str, Any]) -> str:
    """A constraints/assumptions question, for turns held open past the point
    where the six schema fields are already resolved."""
    template = DEEPENING_QUESTIONS[turn_index % len(DEEPENING_QUESTIONS)]
    persona = schema.get("target_persona")
    persona = persona if isinstance(persona, str) and persona else "your users"
    return template.format(target_persona=persona)


def _is_social_message(msg: models.ChatMessage) -> bool:
    """True for assistant messages persisted by a social turn.

    Social assistant messages carry ``"social": true`` in their stored JSON.
    Anything unparseable is treated as substantive — the conservative choice,
    since substantive turns are the ones bounded by MAX_CLARIFICATION_TURNS.
    """
    if msg.role != "assistant":
        return False
    try:
        data = json.loads(msg.message)
    except (TypeError, ValueError):
        return False
    return isinstance(data, dict) and bool(data.get("social"))


def _social_pivot(
    result: dict[str, Any],
    schema: dict[str, Any],
    assistant_turns: int,
) -> tuple[str, str | None]:
    """The question that steers a social exchange back to the idea.

    Returns ``(question, target_field)`` — ``target_field`` is set only when
    the pivot poses a schema-field question itself, so the caller can record
    it in the asked-fields history (the unknown-detection gate only accepts
    "I don't know" for fields that were actually asked).
    """
    model_question = (result.get("next_question") or "").strip()
    if model_question:
        return model_question, None

    still_open = unresolved_fields(schema)
    if len(still_open) == len(IDEA_SCHEMA_FIELDS):
        # Nothing about the idea captured yet — ask for the idea itself.
        return IDEA_PIVOT_QUESTION, None
    if still_open:
        field = still_open[0]
        return (
            f"Could you tell me about the {field.replace('_', ' ')}?",
            field,
        )
    return _deepening_question(assistant_turns, schema), None


def _recap(schema: dict[str, Any]) -> str:
    """Plain-language recap, used when the model returns nothing usable."""
    known = [
        f"{field.replace('_', ' ')}: {schema[field]}"
        for field in IDEA_SCHEMA_FIELDS
        if not isinstance(schema.get(field), dict) and schema.get(field)
    ]
    if not known:
        return "Here's what I have so far on your idea."
    return "Here's what I have so far — " + "; ".join(known) + "."


@celery_app.task(bind=True)
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

        # This task is about to produce turn number (assistant_turns + 1).
        # Social turns don't count: a greeting or "do you remember me?" must
        # not eat the user's clarification budget.
        assistant_turns = sum(
            1
            for msg in chat_messages
            if msg.role == "assistant" and not _is_social_message(msg)
        )

        # ...but chit-chat can't loop forever either: past this absolute
        # message ceiling the session is forced to conclude.
        #
        # Gated on idea_captured: without it, 20 messages of pure small talk
        # would mark all six fields unknown, emit clarification_ready, and run
        # the entire research pipeline on "hi". A user who never states an
        # idea keeps getting social nudges instead (bounded per user by
        # CLARIFICATION_CHAT_RATE).
        idea_captured = bool(
            (session.clarification_schema or {}).get(IDEA_CAPTURED_KEY)
        )
        force_finish = len(chat_messages) >= MAX_TOTAL_MESSAGES and idea_captured

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
            task="clarification",
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

        existing_schema = session.clarification_schema or {}

        # -------------------------------
        # (A) Intent triage — social messages are answered warmly and steered
        # back, without touching the schema or spending a clarification turn.
        # -------------------------------
        intent = str(result.get("message_intent") or "idea_content").strip().lower()
        if intent not in SOCIAL_INTENTS:
            intent = "idea_content"

        if intent in SOCIAL_INTENTS and not force_finish:
            social_reply = (result.get("social_reply") or "").strip()
            if not social_reply:
                social_reply = SOCIAL_FALLBACK_REPLIES[intent]

            asked_before = list(existing_schema.get(ASKED_FIELDS_KEY) or [])
            pivot_question, pivot_field = _social_pivot(
                result, existing_schema, assistant_turns
            )
            if pivot_field and pivot_field not in asked_before:
                schema_copy = existing_schema.copy()
                schema_copy[ASKED_FIELDS_KEY] = asked_before + [pivot_field]
                session.clarification_schema = schema_copy
                existing_schema = schema_copy

            db.add(models.ChatMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                role="assistant",
                message=json.dumps({
                    "social": True,
                    "mirror_summary": social_reply,
                    "next_question": pivot_question,
                }),
            ))
            db.commit()

            clean_schema, _ = serialize_for_downstream(existing_schema)
            publish_event(
                "clarification_update",
                {
                    "session_id": session_id,
                    "schema": clean_schema,
                    "confidence_score": confidence_score(existing_schema),
                    "message_intent": intent,
                    "mirror_summary": social_reply,
                    "next_question": pivot_question,
                },
            )
            return

        # -------------------------------
        # Merge schema (MVP accumulation)
        # -------------------------------
        incoming_schema = result.get("updated_schema") or {}

        merged_schema = merge_schema(existing_schema, incoming_schema)

        # -------------------------------
        # Backfill idea_description on the first substantive message.
        #
        # The session may have been opened by a greeting, leaving "hi" in
        # idea_description -- which is user-visible as the report's label in
        # the reports list and as its title in the report view. The first
        # idea_content message is the real idea, so it replaces that.
        # -------------------------------
        if not idea_captured:
            latest_user_message = next(
                (
                    msg.message
                    for msg in reversed(chat_messages)
                    if msg.role == "user"
                ),
                None,
            )
            if latest_user_message:
                session.idea_description = latest_user_message
            merged_schema[IDEA_CAPTURED_KEY] = True

        llm_directives = result.get("research_directives")
        asked_before: list[str] = list(existing_schema.get(ASKED_FIELDS_KEY) or [])

        # -------------------------------
        # (B) The user cannot answer — convert the gap into research
        #
        # Gated on asked_before: a field is only ever accepted as unknown if
        # it was actually posed as a question in an earlier turn.
        # -------------------------------
        if result.get("unknown_detected"):
            _mark_fields_unknown(
                merged_schema,
                _unknown_target_fields(result, merged_schema, asked_before),
                llm_directives,
            )

        confidence = confidence_score(merged_schema)

        mirror_summary = (result.get("mirror_summary") or "").strip()
        next_question = (result.get("next_question") or "").strip()

        # -------------------------------
        # (C) Hard stop — the conversation must always conclude
        # -------------------------------
        turn_number = assistant_turns + 1
        out_of_turns = turn_number >= MAX_CLARIFICATION_TURNS
        enough_turns = turn_number >= MIN_CLARIFICATION_TURNS
        # Below the floor, ignore the model's own "I'm done" signals: a real
        # design-thinking pass needs a minimum number of exchanges even once
        # the six fields are technically filled.
        fatigued = bool(result.get("turn_fatigue")) and enough_turns
        ready_by_confidence = confidence >= CONFIDENCE_THRESHOLD and enough_turns

        finishing = ready_by_confidence or out_of_turns or fatigued or force_finish

        if finishing and confidence < CONFIDENCE_THRESHOLD:
            # Turns ran out with fields still open — everything remaining
            # becomes a research directive so the session can still conclude.
            _mark_fields_unknown(
                merged_schema,
                unresolved_fields(merged_schema),
                llm_directives,
            )
            confidence = confidence_score(merged_schema)

        # A turn with nothing to say cannot be shown to the user, and
        # repeating it is how the session stalled before.
        degenerate = not mirror_summary and not next_question

        if finishing:
            # Speak, then pivot to consent — never fall silent.
            mirror_summary = mirror_summary or _recap(merged_schema)
            next_question = CLOSING_QUESTION
        else:
            still_open = unresolved_fields(merged_schema)
            if still_open:
                # One core field still needs asking. Per the prompt's own
                # SCHEMA PROGRESSION RULES, that is always the next question —
                # trust the model's question if it gave one, else ask directly.
                target_field = still_open[0]
                asked_before = list(dict.fromkeys(asked_before + [target_field]))
                if degenerate:
                    mirror_summary = _recap(merged_schema)
                    next_question = (
                        f"Could you tell me about the {target_field.replace('_', ' ')}?"
                    )
            else:
                # All six fields resolved, but we're still below the turn
                # floor -- use the remaining turns to probe constraints and
                # assumptions instead of ending the conversation early.
                mirror_summary = mirror_summary or _recap(merged_schema)
                next_question = next_question or _deepening_question(
                    assistant_turns, merged_schema
                )

            merged_schema[ASKED_FIELDS_KEY] = asked_before

        session.clarification_schema = merged_schema

        # -------------------------------
        # Persist assistant message (JSON ONLY)
        # -------------------------------

        # Build assistant conversational text
        db.add(models.ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role="assistant",
            message=json.dumps({
                "mirror_summary": mirror_summary,
                "next_question": next_question,
            }),
        ))
        db.commit()

        clean_schema, unknown_directives = serialize_for_downstream(merged_schema)

        directives = list(llm_directives or []) if isinstance(llm_directives, list) else []
        for directive in unknown_directives:
            if directive not in directives:
                directives.append(directive)

        # Emit conversational update (UI + orchestrator listening)
        publish_event(
            "clarification_update",
            {
                "session_id": session_id,
                "schema": clean_schema,
                "hard_constraints": result.get("hard_constraints"),
                "hypotheses": result.get("hypotheses"),
                "knowledge_gaps": result.get("knowledge_gaps"),
                "research_directives": directives,
                "confidence_score": confidence,
                "unknown_detected": result.get("unknown_detected"),
                "turn_fatigue": result.get("turn_fatigue"),
                "message_intent": "idea_content",
                "mirror_summary": mirror_summary,
                "next_question": next_question,
            }
        )

        # 🔔 Deterministic stop signal
        if finishing:
            publish_event(
                "clarification_ready",
                {
                    "session_id": session_id,
                    "schema": clean_schema,
                    "hard_constraints": result.get("hard_constraints", []),
                    "hypotheses": result.get("hypotheses", []),
                    "knowledge_gaps": result.get("knowledge_gaps", []),
                    "research_directives": directives,
                    "unknown_detected": result.get("unknown_detected", []),
                    "confidence_score": confidence,
                }
            )

    except Exception as e:
        publish_event(
            "clarification_failed",
            {"session_id": session_id, "error": str(e)},
        )
        raise

    finally:
        db.close()
