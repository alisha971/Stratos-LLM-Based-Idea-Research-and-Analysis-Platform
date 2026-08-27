# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Stratos is an agentic AI platform that turns a vague idea into a structured, citation-backed research report: guided clarification → outline → web research/evidence gathering → section writing → assembled export (PDF/HTML). See [README.md](README.md) for product framing and [architecture.md](architecture.md) for the system diagram.

This repo is a monorepo:

- `stratos-backend/` — FastAPI + Celery backend (the actual implementation).
- `stratos-frontend/` — Next.js 16 / React 19 / Tailwind 4 client. Has its own [stratos-frontend/CLAUDE.md](stratos-frontend/CLAUDE.md) (imports `AGENTS.md`) which Claude Code loads automatically when working in that directory — notably it warns this is a pre-release Next.js with breaking API changes, so check `node_modules/next/dist/docs/` before writing frontend code.
- `stratos-launch-plan/` — planning docs: target architecture, per-worker specs (`workers/W1`..`W9`), prompt specs (`prompts/P1`..`P7`), the integration contract, deployment/security/GTM plans.
- `stratos-mvp-fastship/` — condensed MVP scope, env/key setup, ship timeline, build runbook.
- `stratos-pitch/` — pitch material, not code.
- `.claude/skills/` — Stratos-specific skills (contract guard, deploy, LLM prompts, pipeline debug, security gate, task executor, worker upgrade). Load the relevant one before touching its area, e.g. `stratos-contract-guard` before any API/SSE/auth change.

## Commands

### Backend (`stratos-backend/`)

```powershell
python -m venv .venv
& "..\venv\Scripts\Activate.ps1"      # or .venv, per your setup
pip install -r requirements.txt
python scripts/create_tables.py        # first-time DB bootstrap
uvicorn app.main:app --reload          # run API, http://127.0.0.1:8000
celery -A app.workers.celery_app worker --loglevel=info --pool=solo   # separate terminal; --pool=solo needed on Windows
python -m pytest tests -q              # run all backend tests
python -m pytest tests/test_section_writer_service.py -q   # single test file
```

Requires local Postgres (`localhost:5432`, db `stratos`) and Redis (`localhost:6379`) running first, plus a `stratos-backend/.env` — see [SETUP.md](SETUP.md) for the full first-time setup including required env vars and the 4 AstraDB collections (`embeddings` vector-enabled 384-dim/cosine, `evidence`, `trend_items`, `competitor_insights`).

### Frontend (`stratos-frontend/`)

```bash
cp .env.example .env.local
npm install
npm run dev        # http://localhost:3000, backend must already be running
npm test           # vitest
npm run lint        # eslint, zero warnings enforced
npm run build       # production build (needs internet for Google Fonts)
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs `pytest tests -q` for backend, `npm ci && npm test && npm run build` for frontend, and a committed-secret grep — mirror these before pushing.

## Architecture

Event-driven pipeline coordinated by a central orchestrator, per [architecture.md](architecture.md) and [FOLDER_STRUCTURE_GUIDE.md](FOLDER_STRUCTURE_GUIDE.md):

- **`app/api/`** — thin HTTP layer. `auth.py` (Google token → internal JWT), `orchestrator.py` (session lifecycle: start, clarification chat, consent, status), `sse.py` (`GET /stream/events`, bridges Redis pub/sub → Server-Sent Events), `reports.py`. All routers mount once in `app/main.py` (`auth` → `/auth`, `sse` → `/stream`, `orchestrator` → `/orchestrate`); router modules must not declare their own prefix, to avoid the double-`/orchestrate/orchestrate` bug documented in `Docs/Current Runtime Contract Baseline.md`.
- **`app/services/orchestrator_service.py`** — single source of truth for session state transitions; reacts to worker-completion events published on Redis and dispatches the next stage.
- **`app/workers/`** — Celery tasks, one per pipeline stage: `clarification_worker` → `outline_worker` → `research_worker` → `trend_worker` / `section_worker` → `embedding_worker` → `assembler_worker` → `export_worker`. Registered in `celery_app.py`, which tolerates missing modules at import time (logs and continues) so partial pipelines don't crash Celery startup. `competitor_worker.py` and a few `api/`/`services/` files (`deep_dive.py`, `export.py`, `research.py`, `auth_service.py`, `citation_service.py`, `llm_service.py`, etc.) are still empty stubs — check file contents, not just filenames, before assuming a feature is wired up.
- **`app/db/`** — SQLAlchemy models (`models.py`: users, sessions, chat_messages, reports, sections, sources, source_evidence, competitors, trends, exports), engine (`database.py`), request-scoped session dependency (`session.py`).
- **`app/llm/`** — provider dispatch (`client.py`) with a concrete Groq implementation (`client_groq.py`), and shared prompt templates (`prompts.py`). Longer prompt specs live in `stratos-launch-plan/prompts/P1`–`P7`.
- **`app/utils/`** — cross-cutting: `state_machine.py` (session state enum), `redis_pub.py`/`redis_sub.py` (event fanout — the subscriber drives orchestrator transitions), `jwt_utils.py`, `google_oauth.py`, `rate_limit.py` (slowapi, limits configured in `config.py`: `START_SESSION_RATE`, `CLARIFICATION_CHAT_RATE`, `GLOBAL_DAILY_SESSION_CAP`), `text_cleaner.py`.

Storage split: Postgres for relational/session state, AstraDB for vector embeddings + raw evidence/trend/competitor documents (`app/services/astra_evidence_repository.py`).

**Placement rules**: new endpoint → `app/api/`; new state-transition rule → `orchestrator_service.py` (keep it centralized, don't split workflow logic across files); new background stage → `app/workers/`; new DB entity → `app/db/models.py`; new provider/prompt → `app/llm/`; shared helper → `app/utils/`.

**Integration contract**: `stratos-launch-plan/05-INTEGRATION-CONTRACT.md` is the source of truth for every REST endpoint, payload shape, SSE event, and auth rule — both backend and frontend (`orchestratorClient.ts`, `events.ts`, `chatFlowStore.ts`) must be updated together in the same commit when it changes. Full detail in the `stratos-contract-guard` skill.

Deeper docs live in `stratos-backend/Docs/` (DB schema, per-worker low-level architecture, edge cases, API contracts) and `stratos-launch-plan/` (target architecture, deployment, security plan, GTM). `stratos-backend/Docs/Current Runtime Contract Baseline.md` is a point-in-time snapshot of what's actually wired up vs. planned — treat it as a starting hint, not ground truth, and verify against the actual worker/service files since the pipeline has moved past some of what it lists as "not implemented."
