# 04 — Build Summary & Manual Runbook

> What was implemented for the fast-ship MVP, and the exact step-by-step
> commands to run and test the whole thing locally (Windows / PowerShell).
> For key values and where to get them, see `03-ENV-AND-KEYS.md`.

---

## Part A — What was implemented

### §1 Backend correctness
- **Single route prefix** — removed the double `/orchestrate/orchestrate`; routes are now `/orchestrate/start-session`, `/orchestrate/clarification/chat`, `/orchestrate/clarification/accept-consent`, `/orchestrate/status/{id}`.
- **JSON request bodies** — orchestrator endpoints use Pydantic models (`idea_description`, `{session_id, message}`), not query params.
- **`EXPORTED` state** — added to the enum; assembler/export workers use the enum, no string literals.
- **`session_id` on every SSE event** — enforced centrally in `publish_event` (auto-resolves `report_id → session_id`, cached).
- **Report retrieval** — `GET /reports`, `GET /reports/{id}` (sections → chunks → citations), `GET /exports/{id}/file` (serves the PDF from disk).
- **Outline fix** — section ids are flushed before the `outline_ready` payload (no more null ids).
- **Config/CORS/health** — all config from env, CORS locked to `FRONTEND_ORIGIN`, `GET /healthz`.

### §2 Auth
- Google login **upserts a user** and puts `user_id` in the JWT (`sub`).
- **`current_user_id` dependency** on every protected route + **ownership 404s** (never leaks existence).
- **Session-scoped SSE**: `GET /stream/events/{session_id}?token=<jwt>` — verifies the JWT, checks ownership, forwards only that session's events.
- **Rate limits**: 5/hour start-session, 60/hour chat, plus a **global daily cap** (Redis counter → 503).

### §3 Deploy topology
- **Single-container** `Dockerfile` + `start.sh` (runs API **and** Celery worker together).
- **`docker-compose.yml`** for local Postgres + Redis.
- **CI** (`.github/workflows/ci.yml`): backend tests, a secret-scan, and frontend test+build.
- **Smoke script** `scripts/run_pipeline_smoke.py` (start → consent → PDF, prints PASS/FAIL).

### §4 Frontend
- API client rewritten to the contract (auth header, `fetchReport`, `getExportFileUrl`, session-scoped stream URL).
- Full SSE event union; reducer **appends** streaming chunks; **mocks removed**.
- Real report fetched on `export_done`, rendered with `react-markdown` + citation links.
- PDF download wired; SSE **auto-reconnect** with backoff.
- **Google Sign-In** (`/login`) with a **dev-mode button** for local testing.
- Route protection via Next 16 **`proxy.ts`**; **session resume** on refresh.
- **Landing page** at `/`, app moved to `/app`; failure banner + loading states.

### §5 Security
- **SSRF-guarded fetcher** (`app/utils/safe_fetch.py`) on all scraping (8/8 block tests pass).
- Input **length caps** (2,000 chars) + control-char sanitizer.
- **Production boot guards**: refuses to start with the default `JWT_SECRET` or with `DEV_AUTH_BYPASS=true`.

### Key files touched / added
- Backend: `config.py`, `main.py`, `api/{auth,orchestrator,sse,reports}.py`, `utils/{auth_dep,rate_limit,safe_fetch,sanitize,redis_pub,jwt_utils,state_machine}.py`, `services/{orchestrator_service,research_service}.py`, `workers/{outline,assembler,export}_worker.py`, `db/models.py`, `Dockerfile`, `start.sh`, `docker-compose.yml`, `.env.example`, `scripts/run_pipeline_smoke.py`, `tests/test_safe_fetch.py`.
- Frontend: `lib/api/orchestratorClient.ts`, `lib/sse/{events,useEventStream}.ts`, `lib/state/chatFlowStore.ts`, `lib/auth/session.ts`, `components/chat/ChatShell.tsx`, `components/report/{ReportSplitPanel,PdfDownloadButton}.tsx`, `app/{page,login/page,app/page}.tsx`, `proxy.ts`, `.env.example`.

---

## Part B — Manual run & test steps (Windows / PowerShell)

### 0. One-time prerequisites
- Docker Desktop installed and running.
- Python 3.11+ and Node 20+.
- Backend venv exists at `stratos-backend/venv` (already present).

### 1. Backend env
```powershell
cd C:\Users\hp\Desktop\VS\stratos\stratos-backend
Copy-Item .env.example .env
```
Edit `.env` and set at minimum (see `03-ENV-AND-KEYS.md`):
- `GROQ_API_KEY`, `SERP_API_KEY`
- `ASTRA_DB_API_ENDPOINT`, `ASTRA_DB_APPLICATION_TOKEN`
- Keep `DEV_AUTH_BYPASS=true` (lets you test without Google).
- Leave `DATABASE_URL` / Redis URLs as the docker-compose defaults.

### 2. Start local dependencies
```powershell
docker compose up -d
docker compose ps        # postgres + redis should be "running"
```

### 3. Install deps + create tables
```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\create_tables.py     # prints "Tables created successfully!"
```

### 4. Start the API (terminal 1)
```powershell
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```
Test it:
```powershell
curl http://localhost:8000/healthz      # -> {"ok":true}
```
Open `http://localhost:8000/docs` — confirm paths show a single `/orchestrate`.

### 5. Start the Celery worker (terminal 2)
> On Windows, Celery needs the solo pool.
```powershell
cd C:\Users\hp\Desktop\VS\stratos\stratos-backend
.\venv\Scripts\Activate.ps1
celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```
You should see all tasks registered (clarification, outline, research, trend, section, embedding, assembler, export).

### 6. Smoke-test the whole pipeline (terminal 3)
> This is the fastest end-to-end check — no UI needed. Uses the `dev` token.
```powershell
cd C:\Users\hp\Desktop\VS\stratos\stratos-backend
.\venv\Scripts\Activate.ps1
python scripts\run_pipeline_smoke.py
```
Expected: `PASS: full pipeline produced a PDF in <n>s`.
If it fails, the message says which stage — check the worker terminal logs.

### 7. Frontend env + run (terminal 4)
```powershell
cd C:\Users\hp\Desktop\VS\stratos\stratos-frontend
Copy-Item .env.example .env.local
npm install
npm run dev                 # http://localhost:3000
```
Leave `NEXT_PUBLIC_GOOGLE_CLIENT_ID` empty to use the dev-mode button.

### 8. Full manual UI test
1. Open `http://localhost:3000` → landing page loads.
2. Click **Join the beta** → `/login`.
3. Click **Continue in dev mode** → lands on `/app`.
4. Type an idea, e.g. *"AI meal planner for diabetics"*, and send.
5. Answer the clarifying question(s); when the **consent card** appears, click **Start research**.
6. Watch the progress timeline and sections **stream in** on the right panel.
7. When it finishes, the **full cited report** renders; click **Download PDF** → PDF opens.
8. **Refresh mid-run** → the session **resumes** (doesn't reset).
9. Click **Logout** → redirected to `/`; visiting `/app` now bounces to `/login`.

### 9. Automated test suites (optional but recommended)
```powershell
# Backend
cd C:\Users\hp\Desktop\VS\stratos\stratos-backend
.\venv\Scripts\Activate.ps1
python -m pytest tests -q          # includes 8 SSRF block tests

# Frontend
cd C:\Users\hp\Desktop\VS\stratos\stratos-frontend
npm test
npm run lint
```

### 10. Security spot-checks
```powershell
# .env must be gitignored
git check-ignore stratos-backend\.env         # prints the path

# Production boot guard (should ERROR out — that's correct)
cd C:\Users\hp\Desktop\VS\stratos\stratos-backend
$env:ENV="production"; $env:JWT_SECRET="supersecret"
.\venv\Scripts\python.exe -c "import app.config"   # RuntimeError = guard works
Remove-Item Env:ENV, Env:JWT_SECRET
```

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `401` on API calls | Token not set. In dev, use the dev-mode login button (needs `DEV_AUTH_BYPASS=true`). |
| Worker tasks never run | Worker not started, or missing `--pool=solo` on Windows. |
| Pipeline stalls after research | Check the worker terminal for a stack trace; usually a missing `GROQ_API_KEY`/`SERP_API_KEY` or Astra creds. |
| No SSE events in UI | Backend must be running before the app opens the stream; check the "SSE:" badge in the header. |
| `npm run build` font error | Needs internet to fetch Google Fonts; `npm run dev` / `npm test` are unaffected. |
| CORS error in browser | `FRONTEND_ORIGIN` in backend `.env` must exactly match `http://localhost:3000`. |
