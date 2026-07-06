# Implementation checklist

Great, you’re at exactly the right point to **turn this into a clean MVP execution plan**.

Let’s lock this down in a **step-by-step implementation + testing cadence**, so you don’t overbuild and you always know *when to stop*.

I’ll keep this **very practical and scoped to MVP Research Engine only**.

---

# 🎯 MVP GOAL (Research Engine)

By the end, you should be able to say:

> “Given a clarified idea + outline, the system can automatically:
> 
> - search the web
> - scrape relevant pages
> - extract evidence
> - store metadata in Postgres
> - store raw evidence in Astra
> - signal readiness to the next pipeline stage.”

Nothing more. Nothing less.

---

# 🧩 PHASED IMPLEMENTATION PLAN (WITH TEST POINTS)

---

## **PHASE 0 — Pre-flight (5–10 min)**

### ✅ Verify assumptions (once)

- Redis running
- Celery worker starts
- Postgres migrations applied
- `sources` and `source_evidence` tables exist
- `run_outline` already works (✅ confirmed)

🧪 **No testing needed here** — just sanity.

---

## **PHASE 1 — Orchestrator fan-out trigger**

### Implement

**Where:** `OrchestratorService`

Add logic that listens for `outline_ready` and triggers research.

You already have:

```python
run_outline.delay(report.id)

```

Now add (via Redis subscriber or direct call):

```python
run_research.delay(report_id)

```

### Success criteria

- Outline finishes
- Research worker receives task

🧪 **Test immediately**

- Run a session end-to-end until outline
- Confirm Celery logs show:
    
    ```
    Task app.workers.research_worker.run_research received
    
    ```
    

👉 **Stop here if it doesn’t trigger. Fix before moving on.**

---

## **PHASE 2 — Query generation (deterministic MVP)**

### Implement

**File:** `research_service.py`

```python
def generate_queries(self, clarified_summary: str) -> list[str]:
    return [
        "existing solutions",
        "competitor tools",
        "market overview",
    ]

```

No LLM. No cleverness.

### Success criteria

- Queries printed/logged
- Same queries every run

🧪 **Test now**

- Add temporary log
- Confirm queries are generated per run

---

## **PHASE 3 — SERP integration (stub → real)**

### Step 3.1 (MVP Stub)

Return fake results:

```python
return [{
  "url": "https://example.com",
  "domain": "example.com",
  "title": "Example Product",
  "type": "web",
}]

```

🧪 **Test now**

- Research worker completes without crash
- Source row created in Postgres

---

### Step 3.2 (Upgrade — still MVP)

Plug **one** real provider:

- SerpAPI / Tavily / Bing Web Search

Filter:

- Ads
- Duplicate domains

🧪 **Test again**

- Multiple URLs returned
- No duplicate `sources.url`
- Worker completes

---

## **PHASE 4 — Scraping + cleaning**

### Implement

**File:** `research_service.py`

```python
resp = requests.get(url)
cleaned = clean_html(resp.text)

```

Rules:

- Timeout ≤ 10s
- If blocked → skip
- No JS rendering

### Success criteria

- Non-empty cleaned text
- No crashes on bad URLs

🧪 **Test now**

- Mix valid + broken URLs
- Confirm worker does NOT fail entire task

---

## **PHASE 5 — Evidence extraction (Postgres)**

### Implement

- Extract **5–10 snippets**
- Save to `source_evidence`

```python
SourceEvidence(
  source_id=source.id,
  snippet=snippet
)

```

### Success criteria

- `sources` table populated
- `source_evidence` rows linked correctly

🧪 **Test now**

```sql
select * from sources;
select * from source_evidence;

```

Ensure:

- No orphan evidence
- Correct `source_id` FK

---

## **PHASE 6 — Raw evidence storage (Astra)**

### Implement

**File:** `research_service.py`

```python
def save_to_astra(...):
    pass  # insert full cleaned text

```

Store:

- `report_id`
- `source_id`
- `url`
- `raw_text`
- `metadata`

### Success criteria

- Astra collection populated
- Raw text is retrievable

🧪 **Test now**

- Manually query Astra
- Verify text matches scraped content

👉 This is **mandatory before section writer work**.

---

## **PHASE 7 — Events & completion signaling**

### Implement

Emit:

```python
publish_event("research_done", {"report_id": report_id})

```

### Success criteria

- Event visible in Redis subscriber
- Orchestrator receives it

🧪 **Test now**

- Confirm event fires exactly once
- No duplicate emits on retries

---

## **PHASE 8 — Failure handling (MVP-grade)**

### Implement

- Catch per-URL failures
- Do **not** fail entire task unless:
    - DB unavailable
    - Astra unavailable

### Failure cases to test

1. All URLs blocked
2. SERP API rate-limited
3. Astra temporarily down

🧪 **Test now**

- Worker retries
- Final failure emits `research_failed`

---

# ✅ MVP COMPLETION CHECKLIST (RESEARCH ENGINE)

You are **done** when all below are true:

- [x]  Research worker auto-triggers after outline
- [x]  SERP search returns URLs
- [x]  URLs scraped successfully
- [x]  Snippets stored in Postgres
- [x]  Raw text stored in Astra
- [x]  `research_done` event emitted
- [x]  No state mutation inside worker

---

# 🚫 What NOT to build (for MVP)

Do **not** add:

- LLM summarization here
- Relevance scoring
- Competitor detection
- Trend extraction
- Headless browsers
- Chunking / embeddings

All of that comes **later**.

---

# 🔜 What comes immediately after

Once Research MVP is done:

1. **Trend worker** (very similar pipeline)
2. **Competitor worker** (LLM + evidence reuse)
3. **Section writer** (reads Astra evidence)

---

If you want, next we can:

- Write **orchestrator fan-out + barrier logic**
- Design **trend worker MVP**
- Or turn this into a **GitHub checklist / PR plan**

Just tell me which one.