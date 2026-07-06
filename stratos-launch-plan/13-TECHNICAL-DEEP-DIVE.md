# 13 — Technical Deep-Dive: How Stratos Actually Works

> This doc explains the system's internals through three professional lenses — **systems design (SDE)**, **agentic AI**, and **RAG** — with the real code as evidence. Read it to genuinely understand the machine (or to prepare to defend it in a technical interview — see `../stratos-pitch/05-INTERVIEW-QA-PREP.md`). Everything here describes the code as it exists today; where the launch plan upgrades something, it's noted as `(→ upgrade: task)`.

---

## Part A — The systems-design lens

### A1. Process topology

Three kinds of processes share nothing but Redis and Postgres:

1. **API process** (`uvicorn app.main:app`) — HTTP endpoints, plus two long-lived concerns: an SSE endpoint that streams Redis events to browsers, and a **background listener thread** started in the FastAPI lifespan that subscribes to the same Redis channel and drives the orchestrator.
2. **Worker processes** (`celery -A app.workers.celery_app worker`) — execute pipeline stages as Celery tasks.
3. **The browser** — a thin client that renders state derived from SSE events plus a few REST calls.

Two Redis logical databases play two very different roles: **DB 0 is the control plane's task queue** (Celery broker/backend — "go do work") and **DB 1 is the event bus** (pub/sub channel `stratos_events` — "work happened"). Keeping commands and events on separate planes is a classic distributed-systems separation; it means a flood of UI events can never delay task dispatch.

### A2. Event-driven choreography with a central brain

The pipeline is **not** a Celery chain/canvas. Each worker finishes by *publishing an event*, and a single subscriber — the orchestrator, via the listener in `app/utils/redis_sub.py` — decides what happens next:

```28:37:stratos-backend/app/utils/redis_sub.py
        if event_type == "clarification_ready":
            db = SessionLocal()
            try:
                OrchestratorService.handle_clarification_ready(
                    db=db,
                    session_id=payload["session_id"],
                    payload=payload,
                )
            finally:
                db.close()
```

This is the **orchestration-over-choreography** hybrid: transport is choreographed (pub/sub), but decisions are centralized in `OrchestratorService`, which owns the state machine. The benefit: every transition lives in one file, so "why did the pipeline move?" always has one place to look. The cost: the listener thread is a single point of coordination inside the API process (fine at one instance; at N instances every instance would react to every event — idempotent handlers make that safe, see A4).

### A3. The state machine as the source of truth

`app/utils/state_machine.py` defines the session's linear lifecycle (`CREATED → CLARIFYING → AWAITING_CONSENT → READY_FOR_RESEARCH → OUTLINE_GENERATED → RESEARCH_RUNNING → WRITING_SECTIONS → READY_FOR_ASSEMBLY → READY_FOR_EXPORT → EXPORTED`). Three design points worth internalizing:

- **State lives in Postgres, not in memory.** Any process can crash and the pipeline's position survives. Handlers re-read the row, check the current state, then transition — the DB row is the lock-free consensus point.
- **HTTP endpoints are guards, not doers.** `POST /clarification/chat` refuses unless the session is in `CLARIFYING`; `accept-consent` refuses unless `AWAITING_CONSENT`. Invalid transitions are rejected at the boundary rather than corrupting mid-pipeline.
- **Fan-out/fan-in:** `handle_outline_ready` fans out research and trend in parallel; `handle_section_done` counts completed sections and only fires `sections_done` when all are finished — a join barrier implemented as a DB count, not an in-memory latch (again: crash-safe). `(→ upgrade: B2.4 adds the trend/research dual gate with timeout.)`

### A4. Idempotency and retry semantics

Celery gives **at-least-once** delivery: a task may run twice (worker died mid-task, retry fired). The codebase handles this with the **delete-before-insert** pattern rather than distributed locks:

- The outline worker deletes existing sections for the report before inserting — replaying it converges to the same rows.
- The section writer does the same for chunks and citations:

```197:205:stratos-backend/app/services/section_writer_service.py
        existing_chunks = (
            self.db.query(models.Chunk)
            .filter_by(section_id=section_id)
            .all()
        )
        for chunk in existing_chunks:
            self.db.query(models.Citation).filter_by(chunk_id=chunk.id).delete()
        self.db.query(models.Chunk).filter_by(section_id=section_id).delete()
        self.db.flush()
```

- Research dedupes by URL against the DB (`is_duplicate_url`) so replays don't double-store sources.

This is "idempotency by convergent writes" — simpler and more robust than trying to build exactly-once, which is the correct engineering call at this scale.

### A5. Fail-soft layering (graceful degradation)

The system is built so **no optional dependency can kill a run**:

- **Astra DB is fully optional** — `AstraEvidenceRepository` checks its own `enabled` state; the section writer transparently falls back to Postgres evidence (`source_mode: "postgres_fallback"` is even recorded on each item, so degraded runs are diagnosable after the fact).
- **LLM query generation** falls back to canned queries rather than failing research (see `generate_queries`'s except branch).
- **Trend provider failures** are per-source: one dead feed doesn't kill the others.
- Every SERP call catches exceptions and returns `[]`.

The design rule visible throughout: *the pipeline's spine (Postgres + Redis + Groq) is mandatory; everything else degrades.*

### A6. Streaming and the read path

Progress streams to the browser as SSE (`GET /stream/events` bridging Redis → `EventSourceResponse`). Two things an architect should note:

1. **Events are notifications, not the data.** The report itself is fetched via REST from Postgres (`→ B2.1`); events only say "something changed". This keeps events small and makes the UI recoverable after disconnects (re-fetch state, resubscribe).
2. **Polyglot persistence with clear roles:** Postgres = relational system of record (sessions, sections, chunks, citations — everything the user's report is rebuilt from); Astra = high-volume semi-structured evidence store (raw scraped text up to 50k chars/doc, ranked bundles); Redis = ephemeral coordination. Each store does what it's shaped for.

---

## Part B — The agentic-AI lens

### B1. Honest classification

Stratos is an **orchestrated multi-stage LLM pipeline with bounded agentic loops** — not an autonomous agent (the DAG is fixed in code; no model ever chooses the next tool), and much more than a wrapper (nine specialized stages, tool use, validation, state). See `../stratos-pitch/01-MARKET-POSITION-AND-CRITIQUE.md` for the market framing. This section maps which agentic *patterns* are genuinely implemented and where.

### B2. Pattern map

| Agentic pattern | Where it's implemented | Mechanics |
|---|---|---|
| **Tool use** | Research, trend, competitor workers | LLM generates *parameters* (search queries); deterministic code executes the tools (SerpAPI, scrapers, feeds). The model never holds credentials or invokes tools directly — a deliberate capability boundary |
| **Bounded reflection loop** | Clarification worker | Ask → merge answer into schema → recompute confidence → loop until threshold (0.95) or gate. The termination condition is deterministic code, not model judgment `(→ W1-C1 makes the score semantic but keeps deterministic stopping)` |
| **Generate–verify–repair loop** | Section writer | Draft → programmatic validation → on failure, regenerate **with the failure reason injected into the prompt** — genuine self-correction with an external (non-LLM) critic: |
| **Planner/executor split** | Outline worker → section workers | One stage plans the document structure; N executors each own one section with a narrow context. Classic task decomposition |
| **Working memory** | `Session.clarification_schema`, clarified summary | Structured state accumulated across turns and passed forward — memory as a DB column, not a context-window trick |
| **Guardrails** | JSON parsing (`_parse_json` strips code fences, rejects non-objects), state-machine endpoint guards, citation validation | All LLM output passes a strict parse-and-validate boundary before touching the DB |

The repair loop's prompt injection of the critic's verdict:

```108:114:stratos-backend/app/services/section_writer_service.py
        prompt = self._build_prompt(context)
        if repair_reason:
            prompt += (
                "\n\nREPAIR REQUIRED:\n"
                f"{repair_reason}\n"
                "Regenerate the full JSON so the section is valid."
            )
```

### B3. The verifier is deterministic — that's the point

The most important agentic-design decision in the codebase: **the critic that judges LLM output is regex-and-set-logic, not another LLM.** `validate_section_draft` enforces, mechanically: chunks exist and are sequentially indexed; every chunk cites at least once; every inline `[CIT-###]` marker exists in the allowed map; every citation's `source_id` maps to real evidence; inline markers and the structured citations array agree in both directions; content keywords match the section title and don't drift into sibling sections. A deterministic verifier can't be sweet-talked by the generator — which is exactly the failure mode of LLM-judges-LLM setups. `(→ W6-S2 adds an LLM claim-level auditor ON TOP of, not instead of, this layer — defense in depth.)`

### B4. What full agency would add, and why it's deferred

Dynamic replanning ("research came back thin → change strategy") exists only as one bounded reflection round in the upgrade plan (`W3-R6`). Autonomous tool selection, open-ended loops, and self-extending plans are deliberately absent: for a product selling *verifiability with bounded cost per run*, unbounded model-directed control flow is a liability, not a feature. The architecture leaves clean seams for it (the orchestrator is one class; tool calls are already parameterized), so this is a choice, not a limitation of skill.

---

## Part C — The RAG lens

### C1. Stratos is RAG — currently without vectors

The canonical RAG loop is *ingest → index → retrieve → augment → generate → attribute*. Stratos implements every stage; the index is lexical rather than dense `(→ W7 adds vectors)`:

| RAG stage | Stratos implementation |
|---|---|
| Ingestion | SERP fan-out + page scraping (C2 below) |
| Chunking | Snippet extraction (line-level heuristics) + raw text capped at 50k chars |
| Indexing | Astra documents keyed by report/source; retrieval by report_id + keyword scoring (no embedding index yet) |
| Retrieval + ranking | `EvidenceRanker` (C3) building **precomputed per-section bundles** |
| Augmentation | Evidence blocks with citation markers injected into the section prompt |
| Generation | Groq `llama-3.1-8b-instant`, temperature 0.2, JSON mode |
| Attribution | The full citation lifecycle (C4) — the part most RAG systems skip |

A distinctive choice: retrieval is **precomputed per section** (evidence bundles built once after research, stored in Astra) rather than at generation time. That trades freshness for determinism and debuggability — you can inspect exactly what evidence a section was allowed to use, which is the right trade for an auditable product.

### C2. The scraper, mechanically

Ingestion in `research_service.py` is a four-stage funnel:

1. **SERP normalization:** three Google engines per query (web, news via `tbm=nws`, patents via `tbm=pts`), each result normalized to `{url, domain, title, snippet, type}`. Failures return `[]` — a dead engine costs coverage, not the run.
2. **Dedupe at the door:** `is_duplicate_url` checks Postgres per `(report_id, url)` before any fetch is spent.
3. **Fetch + clean:** `requests.get` with a 10 s timeout and a desktop browser User-Agent, non-200s dropped, then `clean_html` (BeautifulSoup-based) strips markup to text lines.
4. **Snippet filtering:** a line becomes evidence only if ≥ 40 chars and not starting with navigation boilerplate (`"home"`, `"menu"`, `"login"`, `"subscribe"`…), capped at 5 snippets per page:

```352:360:stratos-backend/app/services/research_service.py
    def _is_valid_snippet(self, text: str) -> bool:
        if not text:
            return False

        t = text.strip().lower()
        return (
            len(t) >= 40 and
            not t.startswith(BAD_PREFIXES)
        )
```

Each Astra evidence doc also gets an `ingestion_quality_score` — +0.5 per useful term, −1.0 per boilerplate term detected in the first 3k chars. **Known weaknesses, stated plainly:** no JS rendering (bare `requests` loses 30–50% of modern pages `→ W3-R2 trafilatura`), the domain extractor is a naive string split, and — most seriously — **no SSRF protection**: the fetcher will follow any URL a search engine returns `(→ security plan §5 — treat as urgent)`.

### C3. The ranker, mechanically

`EvidenceRanker.rank_for_section` turns a pile of evidence into a section's citation-ready bundle. The scoring walkthrough (real numbers from the code):

- **Dedupe first:** case-folded first-180-chars of the quote as a fingerprint — near-identical snippets collapse.
- **Score:** start at 1.0, then:
  - +1.5 × each section-preference term found in the item's title/quote/domain/url haystack
  - +0.75 × each clarified-summary keyword overlap (capped at 6 matches)
  - +1.0 if a news item is being ranked for a trend section
  - −2.0 × each boilerplate phrase ("checking your browser", "free trial"…)
  - −1.5 × each off-topic term
  - items scoring ≤ 0 are discarded entirely
- **Emit:** sort descending, keep top 12, assign stable markers `CIT-001…CIT-012` in rank order.

The marker assignment is where RAG meets attribution — rank position becomes citation identity:

```172:177:stratos-backend/app/services/evidence_ranker.py
        bundle_items = []
        for index, item in enumerate(scored[:limit], start=1):
            item["marker"] = f"CIT-{index:03d}"
            bundle_items.append(item)

        return bundle_items
```

**An honest flaw you should know about (and fix):** the `SECTION_PREFERENCES` and `useful_terms` vocabularies are **hardcoded to a freelancer-marketplace idea** (`"upwork"`, `"fiverr"`, `"freelancer"`…) — clearly overfit to the idea the system was first tested on. For any other topic, ranking silently degrades to generic keyword overlap. `(→ fix: derive section terms from the clarified summary + outline scope_notes — W2-O5's evidence_hints is the designed replacement.)` This is also a favorite interview grill — see the interview doc.

### C4. Citations end to end (the trust pipeline)

The full lifecycle of one citation, across five stages:

1. **Birth (ranking):** an evidence item earns marker `CIT-007` in a section's bundle; the bundle is persisted to Astra.
2. **Contract (prompting):** `_build_prompt` renders each bundle item as a labeled evidence block — marker, source_id, title, url, quote — and the prompt requires every factual claim to carry an inline marker AND a structured `citations` array entry per chunk. The LLM cannot mint new markers because the validator knows the allowed set.
3. **Enforcement (validation):** regex-extract `\[(CIT-\d{3})\]` from each chunk; assert extracted ⊆ allowed, citations array ⊆ allowed, source_ids ⊆ known, and inline ⊆ array (both representations must agree). Any violation → repair loop with the specific reason.
4. **Persistence:** each chunk becomes a `Chunk` row; each citation becomes a `Citation` row (`chunk_id`, `source_id`, `citation_marker`, `quote` — falling back to the evidence quote if the LLM omitted one). The report's citations are now relational data, joinable back to `Source.url`.
5. **Delivery:** the assembler carries markers into the export JSON; the report API serves chunks with their citations; the PDF prints markers `(→ W8-A5 renumbers to a References section; → W9-X4 makes them clickable)`.

What this buys: **provenance is queryable**. "Show me every claim in this report backed by domain X" is a SQL join, not an ML problem. What it doesn't yet buy: *semantic* faithfulness — the format being valid doesn't prove `CIT-007` actually supports the sentence citing it. That gap is exactly `W6-S2` (claim-level entailment audit) and `W6-S3` (numeric guard).

---

## Part D — Worker-by-worker: concepts in one table

| Worker | SDE concept it demonstrates | Agentic concept | RAG concept |
|---|---|---|---|
| Clarification | Multi-turn state accumulation in Postgres; event-driven turn-taking | Bounded reflection loop with deterministic stop | Query understanding (builds the retrieval brief) |
| Outline | Idempotent delete-before-insert; template-constrained generation | Planner in a planner/executor split | Defines retrieval partitions (sections) |
| Research | Provider fan-out, fail-soft, URL dedupe, quality scoring | Tool use (LLM plans queries, code executes) | Ingestion + chunking + indexing |
| Trend | Parallel multi-provider I/O with per-source failure isolation | Tool use | Ingestion of a second corpus type |
| Competitor `(planned)` | Verification-before-persistence (fetch-or-drop) | Tool use + anti-hallucination wall | Entity-centric retrieval |
| Section writer | Transactional chunk/citation persistence; streaming events | Generate–verify–repair with deterministic critic | Augmented generation + attribution |
| Embedding `(stub)` | Graceful no-op stubbing behind an event | — | The missing dense index (W7) |
| Assembler | Fan-in barrier; document composition | `(planned W8: consistency adjudication)` | Cross-chunk coherence |
| Export | Rendering pipeline, artifact storage | — | Provenance presentation |

## Part E — The three questions this architecture answers

If someone asks "why is it built this way?", the whole design reduces to three commitments:

1. **Every claim must be traceable** → precomputed bundles, marker contracts, deterministic validation, relational citations.
2. **No single external failure may kill a run** → fail-soft layering, per-provider isolation, fallback paths recorded in data.
3. **Cost per run must be bounded and predictable** → fixed DAG, deterministic stops, capped fan-outs — which is precisely why it is a pipeline and not an autonomous agent.
