# Clarification Engine

Status: Done

<aside>
💡

- endpoints
- methods
- req/res schema
- errors
- examples
</aside>

Love this question — this is exactly the right time to **lock contracts** and see what’s *actually done* vs *intentionally deferred*.

I’ll give you:

1. **API contract (backend ↔ frontend)**
2. **Event (SSE) contract**
3. **Internal worker handoff contract**
4. **What is DONE**
5. **What is NOT done (by design, MVP-safe)**

No fluff, no future-scope leakage.

---

# 1️⃣ API CONTRACT (Frontend ↔ Backend)

## 1. `POST /orchestrate/start-session`

### Purpose

Create a session and start clarification.

### Request

```
POST /orchestrate/start-session

```

```json
{
  "user_id": "string",
  "idea_description": "string"
}

```

### Response

```json
{
  "session_id": "uuid",
  "report_id": "uuid",
  "status": "CREATED",
  "message": "Session created. Clarification started."
}

```

### Side Effects

- Saves first user message
- Transitions session → `CLARIFYING`
- Enqueues `clarification_worker`

---

## 2. `POST /orchestrate/clarification/chat`

### Purpose

Send a user reply during clarification.

### Request

```
POST /orchestrate/clarification/chat

```

```json
{
  "session_id": "uuid",
  "message": "string"
}

```

### Response

```json
{
  "session_id": "uuid",
  "status": "CLARIFYING"
}

```

### Side Effects

- Appends user message
- Enqueues clarification worker again

⚠️ Frontend **must not** expect immediate AI text here

👉 AI response comes via **SSE**

---

## 3. `POST /orchestrate/clarification/accept-consent`

### Purpose

User confirms clarification is complete → start research.

### Request

```
POST /orchestrate/clarification/accept-consent

```

```json
{
  "session_id": "uuid"
}

```

### Response

```json
{
  "session_id": "uuid",
  "status": "READY_FOR_RESEARCH"
}

```

### Side Effects

- Builds final clarification proposal
- Saves it to `clarified_summary`
- Enqueues **Outline Worker**

---

## 4. `GET /orchestrate/status/{session_id}`

### Purpose

Debug / frontend sync

### Response

```json
{
  "session_id": "uuid",
  "status": "CLARIFYING | READY_FOR_RESEARCH",
  "idea_description": "string",
  "clarified_summary": "json-string | null"
}

```

---

# 2️⃣ SSE EVENT CONTRACT (Backend → Frontend)

Frontend listens to:

```
GET /stream/events

```

---

## Event: `clarification_update`

### Meaning

Clarification is ongoing — ask next question.

```json
{
  "type": "clarification_update",
  "payload": {
    "session_id": "uuid",
    "schema": { ...partial_schema },
    "research_directives": [],
    "confidence_score": 0.67,
    "mirror_summary": "You want to help freelancers...",
    "next_question": "What do freelancers use today?"
  }
}

```

Frontend behavior:

- Render assistant message
- Enable input box

---

## Event: `clarification_ready` 🔥

### Meaning

Clarification is complete — stop asking questions.

```json
{
  "type": "clarification_ready",
  "payload": {
    "session_id": "uuid",
    "schema": { ...final_schema },
    "research_directives": [
      "Investigate current freelance platforms"
    ],
    "confidence_score": 1.0,
    "mirror_summary": "You are building..."
  }
}

```

Frontend behavior:

- Disable chat input
- Show **“Proceed to Research”** CTA
- Call `/clarification/accept-consent` on click

---

## Event: `clarification_completed`

### Meaning

Research has started.

```json
{
  "type": "clarification_completed",
  "payload": {
    "session_id": "uuid",
    "proposal": {
      "schema": { ... },
      "confidence_score": 1.0
    }
  }
}

```

Frontend behavior:

- Transition UI to research progress

---

# 3️⃣ INTERNAL WORKER HANDOFF CONTRACT

## Input to Outline Worker (Celery)

```json
{
  "session_id": "uuid",
  "schema": {
    "project_domain": "...",
    "target_persona": "...",
    "core_problem": "...",
    "current_workaround": "...",
    "proposed_solution": "...",
    "differentiation": "..."
  }
}

```

✔ Comes from `session.clarification_schema`

✔ No dependency on chat history

✔ Deterministic and replayable

---

# 4️⃣ WHAT IS DONE ✅ (MVP COMPLETE)

### Clarification Engine

- ✅ Multi-turn conversation
- ✅ Schema accumulation (merge-safe)
- ✅ Knowledge gap detection
- ✅ Deterministic confidence
- ✅ Deterministic stop
- ✅ Clean SSE streaming
- ✅ Frontend-controlled progression
- ✅ Zero circular imports
- ✅ Stateless worker
- ✅ Clean handoff to next worker

### Architecture Quality

- ✅ Workers are dumb & isolated
- ✅ Orchestrator owns state transitions
- ✅ Frontend owns consent timing
- ✅ No hidden side effects

This is **production-grade MVP**, not a toy.

---

# 5️⃣ WHAT IS NOT DONE (INTENTIONALLY)

These are **explicitly deferred**, not missing:

### ❌ No rejection / edit flow

- User cannot tweak clarification yet
- MVP assumption: accept or restart

### ❌ No research plan editor

- Research directives are internal hints
- Research workers decide what to use

### ❌ No Redis subscribers

- SSE is push-only for now

### ❌ No partial schema rollback

- Schema is append-only in MVP

### ❌ No confidence decay / weighting

- Simple completeness-based confidence only

---

# 🧭 What Comes Next (When You’re Ready)

**Immediate next worker to implement:**

➡️ `OutlineWorker`

It will:

- Read `clarification_schema`
- Generate section structure
- Emit outline SSE events

If you want, next I can:

- Design **OutlineWorker contract**
- Define **ResearchWorker contract**
- Or draw **state machine diagram** from code

You’ve done the hard part.

This system is now **clean, composable, and scalable**.