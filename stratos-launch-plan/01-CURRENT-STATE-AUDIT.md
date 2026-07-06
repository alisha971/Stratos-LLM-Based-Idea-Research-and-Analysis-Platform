# 01 — Current State Audit

> Snapshot date: July 2026. This is what exists in the repo **today**, verified against the actual code (not the older docs in `stratos-backend/Docs/`, some of which are stale).

## 1. What the product does (one paragraph)

A user types a startup/market idea into a chat UI. The backend runs a **pipeline of Celery workers** coordinated by an orchestrator over Redis pub/sub: (1) a clarification worker asks follow-up questions until a confidence threshold is met, (2) after user consent, an outline worker plans report sections, (3) research and trend workers gather evidence from SerpAPI, Hacker News, GDELT, Google News RSS and arXiv, (4) a section-writer worker drafts each section with an LLM (Groq, `llama-3.1-8b-instant`) using ranked evidence bundles with citations, (5) an assembler concatenates sections, and (6) an export worker renders a PDF with ReportLab. Progress streams to the frontend via Server-Sent Events.

## 2. Status legend

- **DONE** — works end to end, needs at most polish
- **PARTIAL** — core logic works but has known gaps
- **STUB** — placeholder that pretends to work
- **MISSING** — does not exist

## 3. Backend (`stratos-backend/`)

### 3.1 Workers (`app/workers/`)

| Worker | Status | Details |
|---|---|---|
| `clarification_worker.py` | DONE | Multi-turn LLM chat, schema accumulation, confidence gate at 0.95, emits `clarification_update` / `clarification_ready`. Persists `ChatMessage` rows. |
| `outline_worker.py` | PARTIAL | LLM call + JSON parsing works; idempotent section insert. But it **hardcodes 7 core sections** regardless of LLM output (+ up to 3 optional from an allowlist), and the `outline_ready` SSE payload can contain `section_id: null` because it is built before the DB flush. |
| `research_worker.py` | DONE | SerpAPI fan-out (web/news/patents), scraping + cleaning, dedupe, Postgres `Source`/`SourceEvidence`, Astra `evidence` writes. Stale TODO comments at top of `research_service.py` — the features they mention are actually implemented. |
| `trend_worker.py` | DONE | Parallel fan-out to HN Algolia, GDELT, Google News RSS, arXiv. Writes Postgres `Trend`/`TrendItem` + Astra `trend_items`. |
| `competitor_worker.py` | MISSING | File does not exist. Dispatch line is commented out in `orchestrator_service.py`. Astra `competitor_insights` has a reader but no writer; Postgres `competitors`/`competitor_features` tables are never populated. The report's "Competitor Landscape" section is always written from generic research evidence. |
| `section_worker.py` | DONE | Builds context from Astra bundles (Postgres fallback), LLM draft + repair loop, citation validation, persists `Chunk` + `Citation`, streams `section_chunk`, emits `section_done`/`section_failed`. |
| `embedding_worker.py` | STUB | Intentional no-op; emits `embedding_skipped`. Needed only for the future "Deep Dive Q&A" feature. |
| `assembler_worker.py` | PARTIAL | Concatenates chunks into `exports/{report_id}.json` and sets report status. Does **not** save final text to the DB and does no LLM polish. |
| `export_worker.py` | PARTIAL | Real ReportLab PDF at `exports/{report_id}.pdf`, writes `ExportRecord`, emits `export_done`. **But there is no HTTP endpoint to download the file** — the PDF is stranded on local disk. |

### 3.2 Services (`app/services/`)

| Service | Status | Details |
|---|---|---|
| `orchestrator_service.py` | PARTIAL | Full state machine and Celery dispatch. Gaps: no gate on `trend_ready` (sections may start before trends land in Astra), competitor dispatch commented out, no handler for `export_done`. |
| `research_service.py` | DONE | LLM query generation with fallback, SerpAPI, scraping, dedupe, Astra persistence. |
| `trend_service.py` | DONE | 4 providers, dedupe/cap, persistence. |
| `section_writer_service.py` | DONE | Context builder, LLM call, strict validation (title alignment, citation integrity, chunk sequencing). Has the only unit tests in the repo. |
| `astra_evidence_repository.py` | PARTIAL | Real `astrapy` client, fail-soft when creds missing. Collections: `evidence`, `evidence_bundles`, `trend_items`, `competitor_insights` (read-only). |
| `evidence_ranker.py` + `evidence_bundle_service.py` | DONE | Heuristic ranking, `CIT-NNN` markers, per-section bundles. |

### 3.3 API (`app/api/` + `app/main.py`)

| Route | Status | Details |
|---|---|---|
| `POST /auth/google` | PARTIAL | Verifies a Google ID token and returns a JWT. Does **not** create/update a `User` row. |
| `GET /stream/events` | PARTIAL | SSE bridge over Redis channel `stratos_events`. **Global firehose** — every connected client receives every user's events. No auth. |
| `POST /orchestrate/orchestrate/start-session` | PARTIAL | Note the **double prefix bug**: `APIRouter(prefix="/orchestrate")` in `orchestrator.py` AND `include_router(prefix="/orchestrate")` in `main.py`. Also: parameters are declared as bare function args (`user_id: str, idea_description: str`), so FastAPI reads them as **query params**, while the frontend sends a JSON body — this mismatch will 422. |
| `POST .../clarification/chat`, `.../accept-consent`, `GET .../status/{id}` | PARTIAL | Same query-param-vs-JSON-body issue; status response lacks `report_id` which the frontend expects. |
| `GET /reports/{report_id}` | MISSING | No way to fetch the assembled report. |
| `GET /exports/{report_id}/file` | MISSING | No way to download the PDF. |

### 3.4 Data layer

- **Postgres** via SQLAlchemy (`app/db/models.py`): `users`, `sessions`, `reports`, `chat_messages`, `sections`, `chunks`, `citations`, `sources`, `source_evidence`, `trends`, `trend_items`, `competitors` (unused), `competitor_features` (unused), `exports`. Schema created with `scripts/create_tables.py` — **no Alembic migrations**.
- **Astra DB** (DataStax, optional/fail-soft): `evidence`, `evidence_bundles`, `trend_items`, `competitor_insights`.
- **Redis**: DB 0 = Celery broker/backend, DB 1 = pub/sub events. **URLs hardcoded to `localhost` in `app/config.py`** — must become env vars before any cloud deploy.
- **State machine** (`app/utils/state_machine.py`): `CREATED → CLARIFYING → AWAITING_CONSENT → READY_FOR_RESEARCH → OUTLINE_GENERATED → RESEARCH_RUNNING → WRITING_SECTIONS → READY_FOR_ASSEMBLY → READY_FOR_EXPORT`. Workers also write raw strings `"READY_FOR_EXPORT"` / `"EXPORTED"` to `report.status`; `EXPORTED` is not in the enum.

### 3.5 External integrations (wired vs listed)

| Dependency | Wired? | Where |
|---|---|---|
| Groq (`llama-3.1-8b-instant`) | Yes | `app/llm/client_groq.py` — the **only** supported provider; `LLM_PROVIDER != "groq"` raises |
| SerpAPI | Yes | `research_service.py` |
| astrapy (Astra DB) | Yes, optional | `astra_evidence_repository.py` |
| gdeltdoc, feedparser, requests, beautifulsoup4 | Yes | trend + research |
| reportlab | Yes | export worker |
| openai, tldextract, passlib, httpx, aiofiles | **No — in requirements.txt but never imported** | remove or wire |
| Embedding model | **None** | embedding worker is a no-op |

### 3.6 Tests & tooling

- One test file: `tests/test_section_writer_service.py` (5 unittest cases, validation logic only, no DB/LLM).
- No pytest config, no API tests, no CI, no Docker, no `.env.example` (env template lives in root `SETUP.md`).

## 4. Frontend (`stratos-frontend/`)

Next.js 16 App Router, React 19, Tailwind 4, Vitest. ChatGPT-style split layout: chat left, report right.

| Area | Status | Details |
|---|---|---|
| `ChatShell.tsx` | PARTIAL | Real REST calls + SSE subscription, stage-driven UI. But login is a fake `demo-token-${Date.now()}`, PDF button shows "not yet enabled", and a mock progress item is injected after consent. |
| `Composer.tsx`, `MessageList.tsx` | DONE | Clean controlled input + message rendering. |
| `ReportSplitPanel.tsx` | PARTIAL | Renders streaming sections; final report body is **hardcoded placeholder text**, never fetched from backend. |
| `PdfDownloadButton.tsx` | STUB | Presentational only. |
| `ClarificationApprovalCard.tsx`, `ResearchProgressTimeline.tsx` | DONE | Consent card + progress timeline. |
| `BackendSequenceMap.tsx` | STUB | Static badges, several literally labeled "(stubbed)". Dev artifact, remove for prod. |
| `orchestratorClient.ts` | PARTIAL | Real fetches but **wrong contract**: sends `idea_input` / `user_input` as JSON body while the backend expects `user_id` + `idea_description` / `message` as query params; expects `session_state`/`report_id` from status which backend doesn't return. |
| `useEventStream.ts` | PARTIAL | Real `EventSource`, dedupe, dispatch. "Reconnect" only flips a status label — it never reopens the connection. Subscribes to the global firehose with no session filter. |
| `chatFlowStore.ts` | PARTIAL | Solid reducer, but: `section_chunk` **replaces** section text instead of appending; `research_done` inserts a mock section; `export_done` sets placeholder report text and ignores `file_url`; `report_assembled`, `sections_done`, `section_writing_started`, `clarification_started`, `outline_accepted`, `trend_failed` are not handled. |
| `login/page.tsx` | STUB | Informational page, no OAuth. |
| State persistence | MISSING | Refresh loses everything; no localStorage/cookies. |
| Landing page, billing UI, session history, error/failed-stage UI | MISSING | — |
| Tests | PARTIAL | 7 passing tests (parser, store, component render). |

## 5. The critical-path list (what actually blocks a usable product)

1. **API contract mismatch** — frontend requests will fail against the real backend. (Fix in docs 03 §B1 and 04 §F1.)
2. **No report/PDF retrieval endpoints** — the pipeline's output is unreachable. (Doc 03 §B2.)
3. **Fake auth everywhere** — no user identity, no route protection, global SSE firehose. (Docs 03 §B4, 04 §F3, 08.)
4. **Hardcoded localhost Redis + local-disk exports** — cannot deploy to cloud as-is. (Doc 03 §B5, §B6.)
5. **No Docker/CI/migrations** — cannot deploy reproducibly. (Doc 03 §B7, doc 07.)
6. **No billing/quotas** — cannot charge. (Doc 08.)

Everything else (competitor worker, embeddings, LLM polish, deep-dive Q&A) is **post-launch**.
