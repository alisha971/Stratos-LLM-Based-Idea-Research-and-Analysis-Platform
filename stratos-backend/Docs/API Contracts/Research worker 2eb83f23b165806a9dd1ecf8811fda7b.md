# Research worker

Status: In progress

Great — let’s do this **cleanly and contract-first**, exactly like we did for outline.

Below is the **final MVP API contract for the Research Worker**, written so that:

- backend engineers can implement it
- orchestrator can rely on it
- frontend can stream progress
- interviewers won’t poke holes in it

No implementation yet — **this is the contract**.

---

# 🧩 RESEARCH WORKER — API CONTRACT (MVP)

> Role reminder
> 
> 
> The Research Worker **collects external evidence** and stores it.
> 
> It does **not** analyze, reason, or decide next steps.
> 

---

## 1️⃣ Triggering the Research Worker

### Internal-only (Celery)

The Research Worker is **never called directly by frontend**.

### Invocation Source

- Orchestrator only

---

## 🔹 Endpoint / Interface

### **Celery Task**

```python
run_research(report_id: str)

```

---

## 🔹 Input Schema

```json
{
  "report_id": "uuid"
}

```

### Validation Rules

- `report_id` must exist
- `report.session_id` must exist
- `session.status == RESEARCH_RUNNING`

> If state is invalid → exit silently (idempotent)
> 

---

## 2️⃣ Progress Events (SSE / PubSub)

The Research Worker **streams progress**, not results.

---

### 🔹 Event: `searching_sources`

```json
{
  "type": "searching_sources",
  "payload": {
    "report_id": "uuid",
    "queries": [
      "best X tools",
      "X competitors",
      "X alternatives"
    ]
  }
}

```

Purpose:

- Frontend shows “Searching the web…”
- Debug visibility

---

### 🔹 Event: `scraping_sources`

```json
{
  "type": "scraping_sources",
  "payload": {
    "report_id": "uuid",
    "total_urls": 12
  }
}

```

Purpose:

- Progress indicator
- Transparency

---

### 🔹 Event: `research_done`

```json
{
  "type": "research_done",
  "payload": {
    "report_id": "uuid",
    "sources_collected": 9,
    "evidence_items": 9
  }
}

```

Purpose:

- Signals completion
- Triggers orchestrator fan-in logic later

---

## 3️⃣ Persistence Contracts

### 🔹 Postgres — `sources` table

Each source row represents **one external URL**.

```json
{
  "id": "uuid",
  "report_id": "uuid",
  "url": "https://example.com",
  "domain": "example.com",
  "type": "serp | article | product | wiki",
  "created_at": "timestamp"
}

```

Rules:

- One row per unique URL per report
- No duplicate domains+URL pairs

---

### 🔹 Astra DB — `evidence` collection

Each evidence document contains **raw extracted content**.

```json
{
  "evidence_id": "uuid",
  "report_id": "uuid",
  "source_id": "uuid",
  "url": "https://example.com",
  "title": "Page title",
  "raw_text": "Cleaned extracted text…",
  "snippets": [
    "Paragraph 1…",
    "Paragraph 2…"
  ],
  "type": "serp | article | product | wiki",
  "domain": "example.com",
  "metadata": {
    "retrieved_at": "timestamp"
  }
}

```

Rules:

- Evidence must reference a valid `source_id`
- Raw text may be truncated
- Snippets optional but recommended

---

## 4️⃣ Error Handling Contract

### 🔹 Hard Errors (Worker-level)

| Error | Behavior |
| --- | --- |
| Report not found | Exit (no retry) |
| Session missing | Exit |
| Invalid state | Exit |
| Search API down | Retry (Celery autoretry) |
| All URLs fail | Still emit `research_done` |

---

### 🔹 Per-URL Failures (Soft)

| Failure | Action |
| --- | --- |
| 403 / blocked | Save snippet only |
| Timeout | Skip URL |
| JS-heavy page | Skip |
| Empty content | Skip |

> Never fail the entire worker for one URL
> 

---

## 5️⃣ Service Method Signatures (Internal)

These are **logical interfaces**, not REST.

```python
def run_research(report_id: str) -> None

```

Supporting helpers (internal only):

```python
def build_search_queries(clarified_summary: str) -> list[str]

def search_serp(query: str) -> list[SearchResult]

def scrape_url(url: str) -> ScrapedPage | None

def save_source_metadata(db, source_data) -> Source

def save_evidence(astra_client, evidence_data) -> None

```

---

## 6️⃣ Example Execution (Happy Path)

### Input

```json
{ "report_id": "abc-123" }

```

### Behavior

1. Build queries
2. SERP returns 12 URLs
3. 9 URLs successfully scraped
4. 9 `sources` rows created
5. 9 `evidence` docs created
6. Emit `research_done`

### Output

```json
{
  "type": "research_done",
  "payload": {
    "report_id": "abc-123",
    "sources_collected": 9,
    "evidence_items": 9
  }
}

```

---

## 7️⃣ What This Worker Does **NOT** Solve

❌ No summarization

❌ No competitor extraction

❌ No trend labeling

❌ No embeddings

❌ No section mapping

❌ No ranking or scoring

❌ No orchestration decisions

Those are **explicitly delegated** elsewhere.

---

## 8️⃣ Failure Paths (Required)

### ❌ Failure Path 1 — SERP API down

- Search API returns 500
- Worker retries (Celery autoretry)
- After max retries → worker fails
- Orchestrator can retry later

---

### ❌ Failure Path 2 — All URLs blocked

- SERP succeeds
- Scraping fails for all URLs
- Worker still emits `research_done`
- Evidence count = 0

> Pipeline continues — system is resilient.
> 

---

## 9️⃣ Success Criteria (Acceptance Tests)

### ✅ Functional

- Sources saved in Postgres
- Evidence saved in Astra
- No duplicate sources
- Worker completes without crashing

---

### ✅ Behavioral

- Emits progress events
- Does not mutate session/report state
- Can be retried safely
- Does not block pipeline

---

### ✅ Architectural

- Stateless worker
- Orchestrator-controlled flow
- Clear separation of concerns
- Extensible later

---

## 🔒 Final Lock-In Statement

> The Research Worker is a pure data acquisition worker.It gathers evidence, stores it, and stops.
> 

If this contract looks good to you, the **next step** should be:

➡️ **Write `research_worker.py` skeleton + TODOs**

(or)

➡️ **Design orchestrator fan-in logic for research/trend/competitor**

Tell me which one you want to tackle next.