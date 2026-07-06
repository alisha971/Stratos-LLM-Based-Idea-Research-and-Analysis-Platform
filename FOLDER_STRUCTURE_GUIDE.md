# Stratos Folder Structure Guide

This document explains where each major piece of backend logic lives today so future work can be added in the right place.

## Purpose

- Provide a fast navigation map for developers.
- Clarify responsibilities of each folder.
- Reduce accidental coupling and misplaced code.

---

## Repository Root

### `README.md`
- Product vision and high-level project scope.

### `architecture.md`
- System-level architecture and intended data flow.

### `SETUP.md`
- Local setup instructions and run commands.

### `stratos-backend/`
- Main backend implementation.

---

## `stratos-backend/`

### `requirements.txt`
- Python dependencies for API, workers, DB, and AI integrations.

### `.env`
- Runtime configuration and secrets (DB, Redis, OAuth, JWT, LLM, search API keys).

### `scripts/create_tables.py`
- One-time table creation bootstrap using SQLAlchemy metadata.

### `Docs/`
- Product and implementation docs, API contracts, and planning notes.

---

## `stratos-backend/app/` (Application Code)

### `main.py` (Application Bootstrap)
- Creates FastAPI app.
- Registers routers from `api/`.
- Starts Redis event listener thread on startup.

### `config.py` (Configuration Layer)
- Loads and exposes environment-based settings.
- Central source for DB URL, Redis URLs, provider flags, and API keys.

### `worker.py` (Celery Entrypoint)
- Lightweight import entry for Celery process startup.

---

## `app/api/` (HTTP Interface Layer)

### `auth.py`
- Authentication endpoint(s).
- Google token verification -> internal JWT issuance flow.

### `orchestrator.py`
- API surface for session lifecycle:
  - Start session
  - Clarification chat turn
  - Accept clarification consent
  - Fetch session status

### `sse.py`
- Real-time Server-Sent Events endpoint.
- Streams backend events to clients via Redis Pub/Sub integration.

---

## `app/services/` (Business Logic Layer)

### `orchestrator_service.py`
- Core workflow coordinator.
- Source of truth for session transitions.
- Triggers background workers and reacts to worker-completion events.

### `research_service.py`
- Research domain logic:
  - Query generation
  - SERP retrieval
  - Scraping and text extraction
  - Evidence/source persistence helpers

---

## `app/workers/` (Asynchronous Processing Layer)

### `celery_app.py`
- Celery app configuration.
- Task registration/import wiring.

### `clarification_worker.py`
- Multi-turn clarification intelligence.
- Schema accumulation and confidence-based stop/ready signal.

### `outline_worker.py`
- Generates normalized report outline sections from clarified summary.

### `research_worker.py`
- Executes research retrieval flow.
- Processes search results and stores evidence metadata.

---

## `app/db/` (Persistence Layer)

### `database.py`
- SQLAlchemy engine and base setup.

### `session.py`
- Request-scoped DB session provider for FastAPI dependencies.

### `models.py`
- All relational models:
  - Users, sessions, chat messages
  - Reports, sections, chunks, citations
  - Sources and source evidence
  - Competitor and trend entities
  - Export records

---

## `app/llm/` (Model Integration Layer)

### `client.py`
- Provider router/dispatcher for LLM calls.

### `client_groq.py`
- Concrete Groq chat completion implementation.

### `prompts.py`
- Prompt templates used by clarification, outline, and research query generation.

---

## `app/utils/` (Cross-Cutting Utilities)

### `state_machine.py`
- Session state enum and lifecycle vocabulary.

### `redis_pub.py`
- Event publishing helper.

### `redis_sub.py`
- Redis event subscriber that triggers orchestration callbacks.

### `google_oauth.py`
- Google OAuth token validation helper.

### `jwt_utils.py`
- JWT creation and verification utilities.

### `text_cleaner.py`
- HTML/text cleanup for scraped content.

### `clarification_schema.py`
- Schema helper artifact (currently secondary to active worker/service flow).

---

## Current Workflow Ownership (Quick Map)

- HTTP entry and transport: `app/api/`
- Workflow state transitions: `app/services/orchestrator_service.py`
- Async execution: `app/workers/`
- Event fanout/streaming: `app/utils/redis_pub.py`, `app/utils/redis_sub.py`, `app/api/sse.py`
- Persistent models and DB access: `app/db/`
- LLM and prompt behavior: `app/llm/`
- Search/scrape/evidence logic: `app/services/research_service.py`, `app/workers/research_worker.py`

---

## Development Placement Rules

Use these rules to decide where new code should go:

- New API endpoint -> `app/api/`
- New workflow rule or state transition -> `app/services/orchestrator_service.py`
- New long-running/background step -> `app/workers/`
- New database entity or relation -> `app/db/models.py`
- New provider integration or prompt -> `app/llm/`
- Shared helper (JWT, parsing, normalization, event helper) -> `app/utils/`
- Pure project/process documentation -> `Docs/` or root markdown docs

---

## Notes for Future Expansion

- Missing worker modules referenced in Celery config should be added under `app/workers/` before enabling related pipeline stages.
- Keep orchestration state transitions centralized in `orchestrator_service.py` to avoid split-brain workflow logic.
- Keep request handlers thin in `app/api/`; move business logic into services/workers.
- Treat `Docs/` as the contract source when implementing unfinished workers and APIs.
