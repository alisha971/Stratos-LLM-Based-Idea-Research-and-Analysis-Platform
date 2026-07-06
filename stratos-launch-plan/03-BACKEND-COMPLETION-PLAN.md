# 03 — Backend Completion Plan

> Ordered micro-tasks to take `stratos-backend/` from its current state to production-ready. Work **top to bottom**; each task lists the files to touch and how to verify. Keep doc 05 (Integration Contract) open — every endpoint/payload here must match it exactly.
>
> Prerequisite for local work: Postgres + Redis running (use the docker-compose from task B7.1 or local installs per `SETUP.md`), plus `GROQ_API_KEY` and `SERP_API_KEY` in `stratos-backend/.env`.

---

## Phase B1 — Fix the API contract (1 day)

### B1.1 Remove the double route prefix

- **File:** `app/api/orchestrator.py` — change `APIRouter(prefix="/orchestrate", ...)` to `APIRouter(tags=["Orchestrator"])` (no prefix).
- **File:** `app/main.py` — keep `include_router(orchestrator.router, prefix="/orchestrate")`.
- **Verify:** `uvicorn app.main:app` then open `http://localhost:8000/docs` — paths must be `/orchestrate/start-session` etc., with a single `orchestrate`.

### B1.2 Switch orchestrator endpoints to JSON bodies (Pydantic models)

Today the endpoints declare bare `str` parameters, so FastAPI treats them as query params. The frontend sends JSON bodies. Fix the backend to accept JSON:

- **File:** `app/api/orchestrator.py` — add Pydantic request models and use them:

```python
from pydantic import BaseModel

class StartSessionRequest(BaseModel):
    idea_description: str

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ConsentRequest(BaseModel):
    session_id: str
```

- `start_session` takes `body: StartSessionRequest` (the `user_id` will come from JWT in Phase B4; until then accept an optional `user_id` field defaulting to `"dev-user"`).
- Responses must match doc 05 §3 exactly — in particular `GET /orchestrate/status/{session_id}` must return `report_id` and `report_status` (query the `Report` row for the session).
- **Verify:** `curl -X POST localhost:8000/orchestrate/start-session -H "Content-Type: application/json" -d '{"idea_description":"AI meal planner for diabetics"}'` returns 200 with `session_id`, `report_id`, `status`.

### B1.3 Normalize the state enum

- **File:** `app/utils/state_machine.py` — add `EXPORTED = "EXPORTED"` to `SessionState`.
- **Files:** `app/workers/assembler_worker.py`, `app/workers/export_worker.py` — replace string literals `"READY_FOR_EXPORT"` / `"EXPORTED"` with `SessionState.READY_FOR_EXPORT.value` / `SessionState.EXPORTED.value`.
- **Verify:** `rg '"READY_FOR_EXPORT"|"EXPORTED"' app/workers/` returns nothing.

### B1.4 Ensure every SSE payload carries `session_id`

- Audit every `publish_event(...)` call site (`rg publish_event app/`). Any payload missing `session_id` gets it added (workers receive `session_id` or can read it from the report row).
- **Verify:** `rg -A5 'publish_event' app/ | rg -c session_id` — count matches call-site count; then run a session and watch `redis-cli -n 1 subscribe stratos_events` — every event JSON must contain `session_id`.

---

## Phase B2 — Make the report reachable (1–2 days)

### B2.1 `GET /reports/{report_id}`

- **File:** `app/api/reports.py` (new) mounted in `main.py` with no extra prefix.
- Returns the shape in doc 05 §3.6: report status + ordered sections, each with chunks and citations, straight from Postgres (`Section` → `Chunk` → `Citation`).
- **File:** `app/services/orchestrator_service.py` — add `get_report_view(db, report_id)` doing the query; keep the route thin.
- **Verify:** run a full pipeline (task B8.1 script) then `curl localhost:8000/reports/<id>` returns all sections with text.

### B2.2 `GET /exports/{report_id}/file`

- Same new `reports.py` router. Look up `ExportRecord` for the report; if `file_url` is a local path (dev), return `FileResponse(path, media_type="application/pdf", filename="stratos-report.pdf")`; if it's an R2 object key (after B6), return `RedirectResponse` to a presigned URL.
- 404 with a clear message if no export exists yet.
- **Verify:** browser download of a real PDF after a pipeline run.

### B2.3 Fix the `outline_ready` null-ID payload

- **File:** `app/workers/outline_worker.py` — call `db.flush()` (or commit) **before** building the `sections` list for the event so `section.id` is populated.
- **Verify:** subscribe to Redis during a run; `outline_ready` payload has non-null `section_id` for every section.

### B2.4 Gate section writing on trend completion

- **File:** `app/services/orchestrator_service.py` — in the research/trend completion handlers, track both flags on the session (add two nullable timestamp columns `research_done_at`, `trend_done_at` via the Alembic migration in B7.3, or store in a JSON column). Dispatch section writers only when research is done AND (trend is done OR 90 s have elapsed since research finished — implement the timeout as a Celery countdown task that checks and proceeds).
- Also add a `trend_failed` handler that sets `trend_done_at` (pipeline continues without trends; the report just cites fewer trend items).
- **Verify:** full pipeline run — section writing starts only after both `research_done` and `trend_ready` appear in the event stream.

---

## Phase B3 — Config hygiene (half a day)

### B3.1 All config from env

- **File:** `app/config.py` — replace hardcoded Redis URLs:

```python
REDIS_BROKER_URL = os.getenv("REDIS_BROKER_URL", "redis://localhost:6379/0")
REDIS_PUBSUB_URL = os.getenv("REDIS_PUBSUB_URL", "redis://localhost:6379/1")
EXPORT_STORAGE = os.getenv("EXPORT_STORAGE", "local")  # local | r2
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET", "stratos-exports")
ASTRA_DB_KEYSPACE = os.getenv("ASTRA_DB_KEYSPACE")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
```

- Make `JWT_SECRET` **required** in production: raise on startup if it equals `"supersecret"` and `ENV=production`. Add `ENV = os.getenv("ENV", "development")`.
- **File:** `app/workers/celery_app.py` — read broker URL from settings, not a literal.

### B3.2 Commit `.env.example`

- **File:** `stratos-backend/.env.example` (new) listing every variable from B3.1 plus `DATABASE_URL`, `GROQ_API_KEY`, `SERP_API_KEY`, `GOOGLE_CLIENT_ID`, `ASTRA_DB_API_ENDPOINT`, `ASTRA_DB_APPLICATION_TOKEN`, with placeholder values and one-line comments.

### B3.3 Prune requirements.txt

- Remove unused: `openai`, `tldextract`, `passlib`, `aiofiles` (keep `httpx` — the smoke script in B8.1 will use it). Add: `alembic`, `boto3`, `slowapi`, `python-json-logger`, `sentry-sdk`.
- **Verify:** fresh venv, `pip install -r requirements.txt`, `uvicorn app.main:app` starts, one full pipeline run passes.

### B3.4 CORS middleware

- **File:** `app/main.py` — add `CORSMiddleware` with `allow_origins=[settings.FRONTEND_ORIGIN]`, `allow_credentials=True`, methods/headers `["*"]`.
- **Verify:** browser fetch from `localhost:3000` succeeds without CORS errors.

---

## Phase B4 — Real auth (1–2 days)

### B4.1 Upsert `User` on Google login

- **File:** `app/api/auth.py` — after verifying the ID token, `SELECT` user by `google_sub` (add column if missing) or email; create if absent; update name/picture. Include `user_id` in the JWT claims (`sub`).
- **Verify:** call `/auth/google` with a real ID token (get one from the frontend once F3 is done, or from Google OAuth Playground); a `users` row appears.

### B4.2 Auth dependency + ownership checks

- **File:** `app/utils/auth_dep.py` (new):

```python
from fastapi import Depends, HTTPException, Header
from app.utils.jwt_utils import verify_jwt

def current_user_id(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    payload = verify_jwt(authorization.removeprefix("Bearer "))
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    return payload["sub"]
```

- Apply `user_id: str = Depends(current_user_id)` to every orchestrator/report/export route. `start_session` uses it instead of a request field. Every session/report lookup adds `filter_by(user_id=...)` (join `Report → Session` for report routes) and returns 404 on mismatch (404, not 403, to avoid leaking existence).
- Add `DEV_AUTH_BYPASS=true` env flag that, **only when `ENV=development`**, accepts the literal token `dev` as user `dev-user` — this keeps local testing and the smoke script simple.
- **Verify:** request without a token → 401; with `dev` token in dev → 200; user A cannot fetch user B's session (seed two users manually).

### B4.3 Session-scoped SSE

- **File:** `app/api/sse.py` — change route to `GET /stream/events/{session_id}`. Authenticate via `?token=` query param (browsers can't set headers on `EventSource`) using the same JWT verification; check the session belongs to the user; in the Redis message loop, forward only events whose `payload.session_id == session_id` (this is why B1.4 matters).
- **Verify:** open two sessions in two browser tabs; each tab sees only its own events.

---

## Phase B5 — Rate limiting & quotas (half a day)

### B5.1 slowapi on expensive endpoints

- **File:** `app/main.py` + `app/api/orchestrator.py` — `slowapi` limiter keyed by user id: `5/hour` on `start-session`, `60/hour` on `clarification/chat`.
- **Verify:** 6th `start-session` within an hour returns 429.

### B5.2 Plan quota check (schema only for now)

- Alembic migration (B7.3) adds to `users`: `plan VARCHAR DEFAULT 'free'`, `reports_used_this_month INT DEFAULT 0`, `quota_reset_at TIMESTAMP`, `stripe_customer_id VARCHAR NULL`.
- In `start_session`: reset the counter if `quota_reset_at` passed; 402 with `{"detail": "quota_exceeded"}` if `reports_used_this_month >=` plan limit (free=2, starter=10, pro=40 — constants in `config.py`); increment on successful session creation.
- Billing itself (upgrading plans) is doc 08.
- **Verify:** set a user to 2 used reports on the free plan; `start-session` returns 402.

---

## Phase B6 — Object storage for exports (half a day)

### B6.1 R2 upload in export + assembler workers

- **File:** `app/utils/storage.py` (new) — thin wrapper: `upload_file(local_path, key) -> str` and `presigned_url(key, expires=3600) -> str` using `boto3` with the R2 endpoint (`https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com`). If `EXPORT_STORAGE=local`, both are no-ops returning local paths.
- **File:** `app/workers/export_worker.py` — after rendering, upload `exports/{report_id}.pdf` to key `exports/{report_id}.pdf`; store the **key** in `ExportRecord.file_url`; keep the local file as scratch.
- **File:** `app/api/reports.py` — the file endpoint from B2.2 branches on `EXPORT_STORAGE`.
- **Verify:** with R2 creds set, run a pipeline; object appears in the R2 dashboard; the download endpoint redirects and the PDF opens.

---

## Phase B7 — Infrastructure as code (1–2 days)

### B7.1 docker-compose for local deps

- **File:** `stratos-backend/docker-compose.yml` (new): `postgres:16` (port 5432, volume, `POSTGRES_DB=stratos`) and `redis:7` (port 6379). Nothing else — API/workers run on the host in dev for fast iteration.
- **Verify:** `docker compose up -d` then `python scripts/create_tables.py` succeeds.

### B7.2 Production Dockerfile

- **File:** `stratos-backend/Dockerfile` (new):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Workers use the same image with start command `celery -A app.workers.celery_app worker --loglevel=info --concurrency=4` (set in the hosting platform, doc 07).
- **Verify:** `docker build -t stratos-api .` then `docker run --env-file .env -p 8000:8000 stratos-api` serves `/healthz` (add the trivial `GET /healthz` → `{"ok": true}` route in `main.py` now).

### B7.3 Alembic migrations

- `alembic init alembic`; point `env.py` at `app.db.models.Base.metadata` and `DATABASE_URL`.
- Migration 1: `alembic revision --autogenerate -m "baseline"` against an empty DB — this becomes the canonical schema (retire `scripts/create_tables.py`, but leave it with a deprecation note).
- Migration 2: the B5.2 user columns + `google_sub` + `sessions.research_done_at/trend_done_at`.
- **Verify:** fresh DB + `alembic upgrade head` + full pipeline run works.

### B7.4 GitHub Actions CI

- **File:** `.github/workflows/ci.yml` (new, repo root): on PR/push — job 1: backend (`pip install`, `python -m pytest stratos-backend/tests` after converting the unittest file to run under pytest, which it does natively); job 2: frontend (`npm ci && npm test && npm run build` in `stratos-frontend`).
- **Verify:** push a branch; both jobs green in GitHub Actions.

---

## Phase B8 — Verification harness (1 day)

### B8.1 Pipeline smoke script

- **File:** `stratos-backend/scripts/run_pipeline_smoke.py` (new), using `httpx`:
  1. `POST /orchestrate/start-session` (dev token) with a fixed idea.
  2. Poll `GET /orchestrate/status/{id}` every 3 s until `AWAITING_CONSENT` (answer one canned clarification via `/clarification/chat` if the state stays `CLARIFYING` — send "Target the US market, B2C, subscription pricing").
  3. `POST /clarification/accept-consent`.
  4. Poll until report status is `EXPORTED` (timeout 15 min).
  5. `GET /exports/{report_id}/file` — assert 200/302 and PDF magic bytes `%PDF`.
  6. Print `PASS`/`FAIL` and total runtime; exit code 0/1.
- **Verify:** the script itself is the verification. Run it after every phase from here on.

### B8.2 API tests

- **Files:** `tests/test_api_contract.py` (new) — FastAPI `TestClient` + a SQLite or dockerized-Postgres test DB, Celery `task_always_eager=False` with dispatch mocked. Assert: request/response shapes of all doc 05 endpoints, 401s without token, 404 cross-user access, 402 over quota, 429 rate limit.
- **Verify:** `pytest` green locally and in CI.

---

## Phase B9 — Observability (half a day)

- `sentry-sdk` init in `main.py` and `celery_app.py` (FastAPI + Celery integrations), DSN from env, only when `ENV=production`.
- Swap `logging.basicConfig` for JSON formatter (`python-json-logger`); include `session_id` in worker log context.
- **Verify:** raise a test exception in a worker in a prod-like run; it appears in Sentry.

---

## Post-launch backlog (do NOT do before launch)

1. **Competitor worker** — real SERP-based competitor discovery writing `competitor_insights`; until then consider renaming the outline's "Competitor Landscape" core section to "Market Players" so the generic-evidence content matches the title.
2. **Embedding worker** — real embeddings (e.g. `text-embedding-3-small` or a local MiniLM) into Astra vector collection; unlocks Deep Dive Q&A.
3. Assembler LLM polish pass; multi-provider LLM routing (add OpenAI as fallback when Groq rate-limits); DLQ + admin replay; queue split (llm vs io).
