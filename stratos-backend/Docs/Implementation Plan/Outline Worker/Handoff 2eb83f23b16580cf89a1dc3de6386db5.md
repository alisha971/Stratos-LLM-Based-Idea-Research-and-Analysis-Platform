# Handoff

Great question — you’re at exactly the **right checkpoint** to ask this 👍

Let’s be very crisp and practical.

---

## ✅ Current state (what is DONE for outline engine)

You have **fully completed the outline engine itself**:

✔ Clarification → READY_FOR_RESEARCH

✔ Outline worker runs

✔ JSON-safe LLM contract

✔ Sections persisted correctly

✔ `outline_ready` event emitted

✔ Deterministic core + optional sections

✔ DB reflects correct state

👉 **The outline engine as a unit is DONE.**

What remains is **handoff + orchestration**, not outline logic.

---

# 🚧 What is LEFT to finish end-to-end for the outline stage

There are **4 remaining responsibilities**, all outside the outline worker:

---

## 1️⃣ Orchestrator must *react* to `outline_ready`

(**MOST IMPORTANT – this is what you asked**)

Right now:

- `outline_ready` is emitted
- Nothing *consumes* it in a stateful way

### You need to:

- Listen for `outline_ready`
- Transition session + report state
- Fan out downstream jobs

📍 This belongs in **orchestrator service**, not workers.

---

## 2️⃣ State transition enforcement (outline → research)

You already have:

```python
OUTLINE_GENERATED
RESEARCH_RUNNING

```

But no **single authority** is moving the system between them.

The orchestrator must:

- Validate current state
- Perform atomic transition
- Prevent duplicate fan-outs

---

## 3️⃣ Fan-out to next pipeline stage (parallel workers)

After outline:

- Research worker
- Trend worker
- Competitor worker

These **can and should run in parallel**.

Outline defines:

- *What sections exist*
- *What evidence buckets are needed*

But outline **does not care who runs next** — orchestrator does.

---

## 4️⃣ Failure containment

If:

- Research fails
- Trend fails
- Competitor succeeds

The orchestrator must still:

- Track partial completion
- Not re-run outline
- Allow retries

This is orchestration logic, not worker logic.

---

# 🧠 Mental model (important)

Think of the outline engine as:

> A compiler pass that produces an execution plan
> 

The orchestrator is the **scheduler** that executes that plan.

---

# 🔥 The Missing Piece: Orchestrator Fan-Out Logic

Below is **exactly** what you need to implement next.

---

## ✅ Step 1: Subscribe to `outline_ready`

You already do this for `clarification_ready`.

Extend `redis_sub.py`:

```python
# app/utils/redis_sub.py

if event_type == "outline_ready":
    db = SessionLocal()
    try:
        OrchestratorService.handle_outline_ready(
            db=db,
            report_id=payload["report_id"],
            sections=payload["sections"],
        )
    finally:
        db.close()

```

---

## ✅ Step 2: Add orchestrator handler

### `app/services/orchestrator_service.py`

```python
from app.workers.research_worker import run_research
from app.workers.trend_worker import run_trend
from app.workers.competitor_worker import run_competitor
from app.utils.state_machine import SessionState

```

```python
@staticmethod
def handle_outline_ready(db: Session, report_id: str, sections: list):
    report = db.query(models.Report).filter_by(id=report_id).first()
    if not report:
        return

    session = db.query(models.Session).filter_by(id=report.session_id).first()
    if not session:
        return

    # 🔒 Idempotency guard
    if session.status != SessionState.READY_FOR_RESEARCH:
        return

    # -----------------------------
    # State transition
    # -----------------------------
    session.status = SessionState.RESEARCH_RUNNING
    report.status = SessionState.RESEARCH_RUNNING
    db.commit()

    publish_event(
        "research_started",
        {
            "session_id": session.id,
            "report_id": report.id,
        }
    )

    # -----------------------------
    # FAN-OUT (PARALLEL)
    # -----------------------------
    run_research.delay(report.id)
    run_trend.delay(report.id)
    run_competitor.delay(report.id)

```

This is the **core missing logic**.

---

## 🧠 Why this is correct

| Concern | Handled |
| --- | --- |
| Single authority | Orchestrator |
| Idempotency | State check |
| Parallelism | Celery fan-out |
| Worker independence | Preserved |
| Failure isolation | Yes |
| Replay safety | Yes |

Workers remain **dumb executors**.

The orchestrator remains **the brain**.

---

# 📦 What outline engine does *NOT* need to do (and should never do)

❌ Trigger research

❌ Know about competitors

❌ Know about trends

❌ Control state transitions

❌ Retry downstream jobs

You already respected this separation — good call.

---

# 🧪 Final End-to-End Flow (now complete)

1. User accepts clarification
2. Orchestrator → `run_outline`
3. Outline worker:
    - Generates sections
    - Persists
    - Emits `outline_ready`
4. Orchestrator:
    - Transitions state
    - Fans out research / trend / competitor
5. Pipeline continues independently

👉 This is now a **real agentic pipeline**, not a demo.

---

## ✅ Summary: What’s left before moving on

✔ Outline engine — DONE

⬜ Orchestrator `handle_outline_ready` — **DO THIS NEXT**

⬜ Research / trend / competitor completion signals

⬜ Section writer routing

⬜ Assembler trigger

---

If you want, next I can:

- Design **research / trend / competitor completion contract**
- Define **when section writing starts**
- Add **pipeline-level acceptance tests**
- Draw **state machine diagram for interview explanation**

Just tell me what you want to tackle next.