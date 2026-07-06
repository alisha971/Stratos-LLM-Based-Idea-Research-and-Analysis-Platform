# Confidence Accumulation

Perfect choice 👍

**Confidence score is the right next lever** for an MVP: high signal, low complexity, and it directly enables *deterministic stop + consent* later.

I’ll keep this **MVP-clean** — no over-engineering.

---

## 1️⃣ What confidence_score should mean (MVP definition)

For MVP, **confidence_score answers only one question**:

> “Do we have enough clarity to start research without wasting effort?”
> 

It is **NOT**:

- epistemic certainty
- market validation
- correctness

It is simply **clarity completeness**.

---

## 2️⃣ MVP confidence model (simple & effective)

We base confidence on **schema coverage + unknown handling**.

### Core idea

Each clarified field adds confidence.

Explicit unknowns don’t block confidence — they redirect to research.

---

## 3️⃣ Fields that contribute to confidence

Use only the **Idea Schema** (already stable):

```
project_domain
target_persona
core_problem
current_workaround
proposed_solution
differentiation

```

Not all fields are equally important.

---

## 4️⃣ Recommended MVP weights (practical, not academic)

```python
FIELD_WEIGHTS = {
    "project_domain": 0.10,
    "target_persona": 0.20,
    "core_problem": 0.25,
    "current_workaround": 0.15,
    "proposed_solution": 0.20,
    "differentiation": 0.10,
}

```

Why this works:

- **Problem + Persona** dominate
- Solution matters, but less than problem clarity
- Differentiation is nice-to-have at MVP stage

Weights sum to **1.0** → easy reasoning.

---

## 5️⃣ MVP confidence calculation (authoritative)

### Rule

- If a field is **non-null**, it contributes its full weight
- If null, it contributes **0**
- No partial credit
- No decay logic

### Code (drop-in utility)

```python
# app/utils/confidence.py

FIELD_WEIGHTS = {
    "project_domain": 0.10,
    "target_persona": 0.20,
    "core_problem": 0.25,
    "current_workaround": 0.15,
    "proposed_solution": 0.20,
    "differentiation": 0.10,
}

def calculate_confidence(schema: dict) -> float:
    score = 0.0

    for field, weight in FIELD_WEIGHTS.items():
        if schema.get(field):
            score += weight

    return round(min(score, 1.0), 2)

```

That’s it. No magic.

---

## 6️⃣ Where to plug this in (minimal change)

Inside **`run_clarification`**, after schema merge:

```python
from app.utils.confidence import calculate_confidence

confidence = calculate_confidence(session.clarification_schema)

```

Then:

- store it in the result you emit
- optionally store it in session later (optional for MVP)

### Update SSE payload

```python
publish_event(
    "clarification_update",
    {
        "session_id": session_id,
        "schema": session.clarification_schema,
        "confidence_score": confidence,
        "knowledge_gaps": result.get("knowledge_gaps"),
        "research_directives": result.get("research_directives"),
        "unknown_detected": result.get("unknown_detected"),
        "turn_fatigue": result.get("turn_fatigue"),
    }
)

```

---

## 7️⃣ How this behaves in real conversations

### Example progression

**Turn 1**

```json
target_persona ✔
core_problem ✔

```

Confidence ≈ `0.45`

**Turn 2**

```json
current_workaround ✔

```

Confidence ≈ `0.60`

**Turn 3**

```json
proposed_solution ✔

```

Confidence ≈ `0.80` ✅

At this point:

- clarification is *good enough*
- even if differentiation is missing
- even if user said “I don’t know” earlier

---

## 8️⃣ MVP stopping threshold (recommendation)

Use **one simple rule**:

```
confidence_score >= 0.75

```

That’s high enough to avoid junk research, low enough to avoid user fatigue.

---

## 9️⃣ Why this is the right MVP choice

### ✅ Benefits

- deterministic
- explainable
- fast
- no LLM dependence
- no heuristics
- no UX confusion

### ❌ What we intentionally skip

- partial confidence
- downgrade logic
- contradiction handling
- per-field confidence

Those are **V2+** features.

---

## 10️⃣ Final MVP mental model

> Confidence score measures clarity completeness, not correctness.
> 

Once clarity is sufficient:

- stop clarification
- ask for consent
- start research

That’s exactly what your product promises.

---

### Next logical step (when you’re ready)

From here, the clean progression is:

1. ✅ confidence_score (this)
2. ⏭️ deterministic stop condition
3. ⏭️ consent summary synthesis
4. ⏭️ research plan execution

If you want, say:

> “Let’s wire deterministic stop using confidence”
> 

and we’ll do it cleanly in one pass.