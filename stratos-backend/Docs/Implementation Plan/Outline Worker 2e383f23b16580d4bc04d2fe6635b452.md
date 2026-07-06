# Outline Worker

Status: Done

Got it — thanks for the screenshots. You’re right, and this time we’ll **lock it exactly to your real structure**, not a simplified mental model.

Below is the **correct, repo-faithful implementation guide for the OUTLINE WORKER (MVP)**, rewritten **after correcting the structure mistake**.

I’ll explicitly reference **your actual folders and files**, and answer only what you asked for.

---

[Handoff](Outline%20Worker/Handoff%202eb83f23b16580cf89a1dc3de6386db5.md)

# ⭐ OUTLINE WORKER — IMPLEMENTATION DETAILS (MVP, CORRECT STRUCTURE)

Your **actual structure (simplified)**:

```
app/
├── api/
│   └── orchestrator.py
├── db/
│   ├── database.py
│   ├── session.py
│   └── models.py
├── llm/
│   ├── client.py
│   └── prompts.py
├── services/
│   └── orchestrator_service.py
├── utils/
│   ├── redis_pub.py
│   └── state_machine.py
├── workers/
│   ├── celery_app.py
│   ├── outline_worker.py   👈 FOCUS
│   └── ...
├── main.py

```

---

## 1️⃣ Stubs / TODOs (Exact, File-Accurate)

### 📄 `app/workers/outline_worker.py`

**Purpose:**

Generate the report structure (sections) after clarification is complete.

```python
from sqlalchemy.orm import Session
import json, re

from app.workers.celery_app import celery_app
from app.db.session import SessionLocal
from app.db import models
from app.llm.client import generate_chat
from app.llm.prompts import OUTLINE_PROMPT
from app.utils.redis_pub import publish_event

```

### ✅ Celery task stub (authoritative)

```python
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

```

---

### 📄 Helper (inside same file, MVP-simple)

```python
def parse_outline(raw_output: str) -> list[str]:
    """
    TODO:
    - Extract JSON array if needed
    - Normalize titles
    - Deduplicate
    - Enforce allowed vocabulary
    """

```

---

## 2️⃣ Assumptions (Locked for MVP)

These assumptions **match your clarification engine + orchestrator flow**.

1. **Clarification is finished**
    - `sessions.clarified_summary` is final
    - No partial states handled here
2. **Outline runs once per report**
    - Re-runs are destructive (delete & recreate)
3. **Titles are stable contracts**
    - Downstream workers depend on section titles
    - No user edits in MVP
4. **Outline worker is silent**
    - No streaming “thinking”
    - SSE event only when complete
5. **LLM output is untrusted**
    - Always parsed + filtered

---

## 3️⃣ Dependencies (Real, Not Hypothetical)

### Runtime dependencies

| Dependency | Why |
| --- | --- |
| Postgres | Store sections |
| Celery | Async execution |
| Redis | PubSub (SSE) |
| LLM | Outline inference |

---

### Code dependencies (actual imports)

- `models.Report`
- `models.Section`
- `SessionLocal`
- `generate_chat`
- `OUTLINE_PROMPT`
- `publish_event`

---

### Explicit non-dependencies

❌ Astra DB

❌ Research data

❌ Competitors

❌ Trends

❌ Chunks / citations

❌ Chat history

This is **intentional decoupling**.

---

## 4️⃣ Edge Case List (MVP-Covered)

### 1. Clarified summary missing

**Cause:** Orchestrator misfires

**Handling:**

- Raise error
- Emit `outline_failed`
- Abort pipeline

---

### 2. Extremely vague summary

Example:

> “I want to build an app.”
> 

**Handling:**

- Generate only **non-negotiable sections**
- Skip derived sections

---

### 3. LLM invents creative sections

Example:

> “Philosophical Implications”
> 

**Handling:**

- Drop anything outside approved lists

---

### 4. Duplicate / overlapping titles

Example:

- “Competitors”
- “Competitor Analysis”

**Handling:**

- Normalize to canonical title
- Deduplicate

---

### 5. Task retries

**Handling:**

- Safe because of delete-and-recreate logic

---

### 6. Partial DB write

**Handling:**

- Transaction
- All-or-nothing section insert

---

## 5️⃣ Why This Structure Was Chosen (Repo-Level Reasoning)

### Why `outline_worker.py` lives in `workers/`

- Long-running
- Retryable
- Async
- Side-effect heavy
- Not HTTP-bound

This matches:

- clarification_worker
- research_worker
- competitor_worker

Consistency matters.

---

### Why outline logic is NOT in orchestrator

- Orchestrator = state + routing
- Workers = execution
- Keeps orchestrator thin and deterministic

---

### Why outline exists at all

Because:

- UI needs section placeholders
- Orchestrator needs structure to fan out work
- Assembler needs deterministic section ordering

Without outline:

- implicit structure
- brittle assembly
- unclear UI state

---

## 6️⃣ What Was Dropped (Intentionally)

### ❌ Section-to-worker mapping metadata

Why:

- Overkill for MVP
- Section titles are enough
- Reduces coupling

---

### ❌ Streaming outline “thinking”

Why:

- UX sugar
- Clarification already covers “AI thinking”
- Keeps worker simpler

---

### ❌ User-editable outline

Why:

- Dependency tracking nightmare
- Requires recomputation logic
- MVP scope killer

---

## 7️⃣ What Can Be Improved Later (Clean Evolution)

### V2 / V3 upgrades (safe)

1. **Section intent metadata**
    
    ```json
    { "intent": "competitor_analysis" }
    
    ```
    
2. **Per-section readiness**
    - Start writing sections as data arrives
3. **Editable outline**
    - Reorder / remove sections
    - Requires re-run logic
4. **Outline explanation**
    - “Why this section exists”
5. **Incremental outline expansion**
    - Advanced, but future-safe

---

## 8️⃣ Final Mental Model (Authoritative)

> Outline Worker = Structural contract generator
> 
- It defines *what will exist*
- Not *how* or *when* it is filled
- Everything downstream plugs into this structure

This is **exactly correct for MVP** and does **not block future sophistication**.

---

If you want next, I can:

- write the **actual `outline_worker.py` code** (ready to paste)
- design the **OUTLINE_PROMPT**
- or do the **same repo-accurate breakdown** for Research / Competitor / Trend workers

Just tell me which one.