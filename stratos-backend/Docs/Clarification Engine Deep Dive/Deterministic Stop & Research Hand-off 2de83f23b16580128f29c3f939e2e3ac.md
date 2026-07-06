# Deterministic Stop & Research Hand-off

Perfect — this is the **right moment to freeze scope and finish Clarification cleanly**.

I’ll be ve ry explicit, minimal, and production-sane.

---

# ✅ FINAL MVP DECISION (Locked)

For **MVP**, the Clarification Engine must do **only these 4 things**:

1. **Accumulate schema** (already done ✅)
2. **Compute deterministic confidence** (already done ✅)
3. **Deterministically stop** when ready (NEW 🔥)
4. **Hand off a clean research payload** to the next worker (NEW 🔥)

❌ No rejection flow

❌ No tweaking

❌ No clarification_service

❌ No Redis subscribers

❌ No circular imports

Frontend **only**:

- Displays SSE
- Calls `/accept-consent` when user clicks “Proceed”

---

# 🔁 FINAL FLOW (MVP, deterministic)

```
User → clarification/chat
      ↓
Clarification Worker (LLM)
      ↓
Schema merge + confidence compute
      ↓
IF confidence >= threshold OR turn_fatigue:
      → emit "clarification_ready" event
      → stop asking questions
      ↓
Frontend shows summary + "Proceed"
      ↓
User clicks Proceed
      ↓
/clarification/accept-consent
      ↓
Orchestrator enqueues OutlineWorker

```

**Key rule:**

👉 **Worker never calls Orchestrator**

👉 **Orchestrator never listens to SSE**

👉 **Frontend is the trigger**

This removes **all loops**.

---

# 🧠 What becomes the “Research Proposal”?

You already have it.

👉 **The proposal is DERIVED, not stored incrementally**

It is computed **once**, at stop time, from:

- `session.clarification_schema` (persisted)
- latest `research_directives` (from LLM response)
- `confidence_score` (computed)

No extra DB fields needed.

`clarified_summary` will be written **once**, at stop.

---

# ✅ EXACT CHANGES YOU NEED (ONLY 3 FILES)

---

## 1️⃣ clarification_worker.py (FINAL)

### 🔥 Add deterministic stop + ready event

### 🔥 DO NOT call Orchestrator

```python
CONFIDENCE_THRESHOLD = 0.95
MAX_TURNS = 5

```

Add turn count:

```python
turn_count = len([m for m in chat_messages if m.role == "assistant"])

```

Modify the bottom of `run_clarification`:

```python
ready = (
    confidence_score >= CONFIDENCE_THRESHOLD
    or result.get("turn_fatigue") is True
    or turn_count >= MAX_TURNS
)

event_type = "clarification_ready" if ready else "clarification_update"

publish_event(
    event_type,
    {
        "session_id": session_id,
        "schema": merged_schema,
        "research_directives": result.get("research_directives"),
        "confidence_score": confidence_score,
        "mirror_summary": result.get("mirror_summary"),
        "next_question": None if ready else result.get("next_question"),
    }
)

```

🚫 **No orchestrator import**

🚫 **No consent logic here**

---

## 2️⃣ orchestrator_service.py (SIMPLIFIED & CLEAN)

### 🔥 Orchestrator ONLY reacts to API calls

```python
class OrchestratorService:

    @staticmethod
    def accept_consent(db: Session, session: models.Session):
        if session.status != SessionState.CLARIFYING:
            raise HTTPException(400, "Invalid state")

        # Build final proposal ONCE
        proposal = {
            "schema": session.clarification_schema,
            "confidence_score": compute_confidence(session.clarification_schema),
        }

        session.clarified_summary = json.dumps(proposal, indent=2)
        session.status = SessionState.READY_FOR_RESEARCH
        db.commit()

        # 🔥 Enqueue next worker
        from app.workers.outline_worker import run_outline
        run_outline.delay(session.id)

        publish_event(
            "clarification_completed",
            {
                "session_id": session.id,
                "proposal": proposal,
            }
        )

```

❌ No request_consent

❌ No evaluate_clarification

❌ No Redis subscription

---

## 3️⃣ api/orchestrator.py (FINAL MVP API)

### Only 3 endpoints matter

```python
@router.post("/clarification/chat")
def clarification_chat(...):
    OrchestratorService.handle_user_message(...)

```

```python
@router.post("/clarification/accept-consent")
def accept_clarification_consent(session_id: str, db: Session = Depends(get_db)):
    session = db.query(models.Session).get(session_id)
    OrchestratorService.accept_consent(db, session)
    return {"status": "research_started"}

```

No `/evaluate`

No `/reject`

---

# 📦 What the NEXT worker receives

Outline / Research worker input:

```json
{
  "schema": {
    "project_domain": "...",
    "target_persona": "...",
    "core_problem": "...",
    "current_workaround": "...",
    "proposed_solution": "...",
    "differentiation": "..."
  },
  "confidence_score": 1.0
}

```

That’s **more than enough** to start research.

---

# ✅ What we just achieved

✔ Deterministic stop

✔ Zero circular imports

✔ Stateless worker

✔ Clean orchestration boundary

✔ Frontend-controlled progression

✔ Ready for production evolution

---

# 🚀 Clarification Engine = DONE

This is a **complete, correct MVP Clarification Engine**.

If you want, next we can:

- Design the **OutlineWorker input contract**
- Add **versioned schema snapshots**
- Or move straight to **ResearchWorker**

Just say the word.