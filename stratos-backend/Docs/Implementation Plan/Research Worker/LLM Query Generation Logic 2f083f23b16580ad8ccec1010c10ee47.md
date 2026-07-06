# LLM Query Generation Logic

Perfect. You’re at **exactly the right moment** to introduce LLM intelligence in a *controlled*, MVP-safe way.

We’ll **only touch query generation**, keep everything else unchanged, and **respect your Groq JSON enforcement**.

I’ll do this in a clean, surgical way.

---

# 🎯 Goal (THIS STEP ONLY)

Replace this:

```python
def generate_queries(self, clarified_summary: str) -> list[str]:
    return [
        "existing solutions",
        "competitor tools",
        "market overview",
    ]

```

with:

> LLM-generated, structured, bounded search queries derived from the clarified summary.
> 

No SERP logic yet. No scraping changes. No orchestration changes.

---

# ⚠️ Important Constraint (Groq)

Your `generate_chat()` **forces**:

```python
response_format={"type": "json_object"}

```

So:

- ❌ Plain text output will FAIL
- ❌ Bullet lists will FAIL
- ❌ “Almost JSON” will FAIL
- ✅ Must be **valid JSON object**

We will design the prompt + parsing **around this**.

---

# ✅ Design Decision (MVP-SAFE)

### LLM output format (STRICT)

```json
{
  "queries": [
    "query 1",
    "query 2",
    "query 3"
  ]
}

```

That’s it.

No nested schemas. No metadata. No creativity here.

---

# 🧠 Query Strategy (MVP)

We will ask the LLM to generate **3–5 high-signal queries** across:

1. Existing solutions
2. Competitors / alternatives
3. Market / industry context
4. (Optional) Pain points / gaps

Bounded. Predictable. Reviewable.

---

# 🧱 Step 1 — Add Prompt

### `app/llm/prompts.py`

```python
RESEARCH_QUERY_PROMPT = """
You are a research assistant.

Your task is to generate concise, high-signal web search queries
based on a clarified product idea.

Rules:
- Return ONLY valid JSON
- Do NOT include explanations
- Do NOT include markdown
- Queries must be suitable for Google/Bing search
- Each query should be short (5–10 words)
- Generate between 3 and 5 queries

Return JSON in this exact format:
{
  "queries": ["query 1", "query 2", "query 3"]
}

Clarified Summary:
{{CLARIFIED_SUMMARY}}
"""

```

This **will pass Groq validation**.

---

# 🧱 Step 2 — Implement LLM Query Generation

### Modify `ResearchService.generate_queries`

```python
from app.llm.client import generate_chat
from app.llm.prompts import RESEARCH_QUERY_PROMPT
import json

def generate_queries(self, clarified_summary: str) -> list[str]:
    if not clarified_summary:
        raise ValueError("Clarified summary missing")

    prompt = RESEARCH_QUERY_PROMPT.replace(
        "{{CLARIFIED_SUMMARY}}",
        clarified_summary
    )

    raw = generate_chat(
        messages=[{"role": "system", "content": prompt}],
        temperature=0.3,
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("LLM returned invalid JSON for research queries")

    queries = data.get("queries")

    if not isinstance(queries, list) or not queries:
        raise ValueError("Missing or invalid 'queries' field")

    # Final hard safety checks
    cleaned = []
    for q in queries:
        if isinstance(q, str) and 3 <= len(q.split()) <= 12:
            cleaned.append(q.strip())

    if not cleaned:
        raise ValueError("No valid research queries generated")

    return cleaned[:5]

```

---

# ✅ Why this is correct

- ✔ Respects Groq’s strict JSON enforcement
- ✔ Deterministic shape
- ✔ Guards against hallucinated garbage
- ✔ Easy to debug
- ✔ Easy to evolve later (weights, query types, etc.)

---

# 🧪 IMMEDIATE TEST PLAN (DO THIS NOW)

### Manual Test (must pass before moving on)

1. Run full flow:
    - Session → Clarification → Consent → Outline → Research
2. Watch Celery logs:
    
    ```
    generated queries: [...]
    
    ```
    
3. Confirm:
    - Queries are relevant to clarified summary
    - 3–5 queries generated
    - No JSON validation errors
4. Confirm research worker continues execution

---

# ❌ Failure Cases You SHOULD Test

| Case | Expected |
| --- | --- |
| Empty clarified summary | Worker fails early |
| LLM returns empty array | Worker retries |
| LLM returns invalid JSON | Worker retries |
| Query list > 5 | Trimmed |

---

# 🧭 What NOT to add yet

Do **NOT**:

- Add query classification
- Add weights or priorities
- Add domain filters
- Add SERP tuning
- Add embeddings

That comes *after* SERP integration.

---

# 🔜 Next Steps (After This Works)

**In order:**

1. 🔌 Integrate real SERP API (Bing / Tavily / SerpAPI)
2. 🧹 Domain filtering
3. 🔁 Duplicate URL detection
4. 🧠 Evidence scoring (later)
5. 📦 Section writers consume Astra evidence

---

If you want, next I can:

- Wire **real SERP integration**
- Add **domain allow/deny list**
- Add **retry-safe deduplication**
- Or review **trend worker parity**

Tell me what you want to tackle next.

Perfect — you’re at the **right checkpoint** to do manual testing now 👍

Below is a **clean, practical, step-by-step manual test plan** for the **LLM-based query generation with fallback**.

This is written so you can literally run these in your local setup and **check DB + logs + SSE**.

---

# ✅ Manual Test Plan — `generate_queries()` (LLM + Fallback)

## Scope

Tests only **query generation logic** inside `ResearchService.generate_queries`.

- ✔ LLM path
- ✔ Validation logic
- ✔ Fallback behavior
- ✔ Pipeline safety
- ❌ Does NOT test SERP / scraping yet

---

## 🔧 Pre-requisites (Before Testing)

1. **Celery worker running**
    
    ```bash
    celery -A app.workers.celery_app worker --loglevel=info --pool=solo
    
    ```
    
2. **Redis running**
    
    ```bash
    redis-server
    
    ```
    
3. **Valid session + report**
    - Clarification completed
    - Consent accepted
    - Outline generated
    - Research automatically triggered
4. **Enable logging**
    
    Add temporary log inside `generate_queries`:
    
    ```python
    print("Generated queries:", cleaned)
    
    ```
    

---

# 🟢 HAPPY PATH TESTS

---

## ✅ Test 1 — Valid LLM JSON response

### Setup

Ensure:

- `RESEARCH_QUERY_PROMPT` instructs JSON output:
    
    ```json
    {
      "queries": [
        "existing task management tools",
        "best alternatives to Notion",
        "market overview of productivity software"
      ]
    }
    
    ```
    

### Action

Trigger research:

```bash
run_research.delay(report_id)

```

### Expected

- No exceptions
- `cleaned[:5]` returned
- Console log shows LLM queries
- `sources` table populated
- SSE events:
    
    ```
    searching_sources
    research_done
    
    ```
    

### Pass Criteria

✔ LLM queries used

✔ Research continues

✔ No fallback triggered

---

## ✅ Test 2 — LLM returns MORE than 5 queries

### LLM Output

```json
{
  "queries": [
    "existing solutions",
    "competitor tools",
    "market overview",
    "pricing comparison",
    "user reviews",
    "open source alternatives"
  ]
}

```

### Expected

- Only first **5** queries used

### Pass Criteria

✔ Length capped at 5

✔ No errors

---

# 🟡 SOFT FAILURE → FALLBACK TESTS

---

## ⚠️ Test 3 — LLM returns invalid JSON

### Force

Temporarily modify prompt to cause plain text output:

```
Here are some queries you can use...

```

### Expected

- JSON parsing fails
- **NO exception thrown to Celery**
- Fallback queries returned:
    
    ```python
    [
      "existing solutions",
      "competitor tools",
      "market overview"
    ]
    
    ```
    

### Pass Criteria

✔ Research continues

✔ No `research_failed` event

✔ Fallback queries used

---

## ⚠️ Test 4 — JSON valid but missing `queries`

### LLM Output

```json
{
  "search_terms": ["foo", "bar"]
}

```

### Expected

- Validation fails
- Fallback used

### Pass Criteria

✔ Fallback triggered

✔ Pipeline does not stop

---

## ⚠️ Test 5 — Queries too short / too long

### LLM Output

```json
{
  "queries": ["hi", "x", "a very very very very very long sentence query"]
}

```

### Expected

- All filtered out
- Fallback triggered

### Pass Criteria

✔ No empty query list returned

✔ Research continues

---

# 🔴 HARD FAILURE TESTS (Correct Behavior)

---

## ❌ Test 6 — `clarified_summary = None`

### Force

Manually nullify in DB:

```sql
UPDATE sessions SET clarified_summary = NULL WHERE id = '...';

```

### Expected

- `ValueError("Clarified summary missing")`
- Celery retries
- Eventually `research_failed` event

### Pass Criteria

✔ Failure is **intentional**

✔ Data integrity protected

---

# 🔁 PIPELINE INTEGRATION TEST

---

## 🔄 Test 7 — End-to-end with outline → research

### Flow

1. Start session
2. Complete clarification
3. Accept consent
4. Outline generated
5. Research auto-starts

### Observe SSE

```
outline_accepted
research_started
searching_sources
research_done

```

### DB Checks

```sql
SELECT * FROM sources;
SELECT * FROM source_evidence;

```

### Pass Criteria

✔ Queries generated

✔ Sources inserted

✔ Evidence saved

---

# 🧪 NEGATIVE OBSERVATION TESTS

---

## ⚠️ Test 8 — LLM API down / timeout

### Simulate

- Kill internet or mock exception in `generate_chat`

### Expected

- Exception caught
- Fallback queries used
- Research continues

### Pass Criteria

✔ No crash

✔ Research still completes

---

# ✅ ACCEPTANCE CRITERIA (MVP)

You can mark this **DONE** if:

- ✔ Research never blocks due to LLM output
- ✔ Fallback always works
- ✔ Hard failures only happen on data corruption
- ✔ Queries are human-reasonable
- ✔ Pipeline completes successfully

---

# 🧠 Final Verdict

> This implementation is MVP-correct, production-safe, and extensible.
> 

You’ve:

- Isolated LLM risk
- Preserved orchestration authority
- Built a resilient research pipeline

Next logical step (when you’re ready):

➡️ **SERP integration + domain filtering**

Say the word and we’ll move there.