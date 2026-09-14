# Stratos Local Setup Guide

This guide covers first-time local setup for the backend in this repository.

## 1) Prerequisites

Install the following first:

- Python 3.10+ (3.11 recommended)
- PostgreSQL (running on `localhost:5432`)
- Redis (running on `localhost:6379`)
- Optional but required for full workflow: valid API keys for Groq, SerpAPI, and Astra
- Optional: a Product Hunt developer token (competitor worker's second discovery source — it runs on Hacker News alone without one)

The backend uses FastAPI, Celery, SQLAlchemy, Redis, and Postgres.

## 2) Python Environment Setup

From the `stratos-backend` directory:

```powershell
python -m venv .venv
# This repo uses a venv at: C:\Users\hp\Desktop\VS\stratos\venv
& "..\venv\Scripts\Activate.ps1"
pip install -r requirements.txt
```

## 3) Configure Environment Variables

Create a `.env` file in `stratos-backend` and set at least:

- `DATABASE_URL`
- `GROQ_API_KEY_ALISHA`
- `GROQ_API_KEY_ENCRIL`
- `SERP_API_KEY`
- `ASTRA_DB_API_ENDPOINT`
- `ASTRA_DB_APPLICATION_TOKEN`
- `GOOGLE_CLIENT_ID`
- `JWT_SECRET`
- `PRODUCT_HUNT_TOKEN` (optional — see below)

Example database URL format:

```text
postgresql://postgres:<password>@localhost:5432/stratos
```

### Where to get each `.env` key (first-time setup)

Use this mapping when setting up on a fresh machine:

- `DATABASE_URL`
  - Source: your local PostgreSQL installation
  - How to set:
    - Create a DB named `stratos`
    - Use your local postgres username/password
    - Format: `postgresql://<user>:<password>@localhost:5432/stratos`
- `GROQ_API_KEY_ALISHA` / `GROQ_API_KEY_ENCRIL`
  - Source: Groq Console API keys — two separate keys/accounts
  - What it's for: `app/llm/client.py` routes each LLM call to one key as
    primary and falls back to the other on failure (rate limit, API error),
    roughly doubling the effective daily token quota. See
    `app/llm/routing.py` for which key/model pair each task uses.
  - How to set:
    - Sign in to [https://console.groq.com](https://console.groq.com) with
      each account
    - Create an API key in each
    - Paste them as `GROQ_API_KEY_ALISHA=...` and `GROQ_API_KEY_ENCRIL=...`
- `SERP_API_KEY`
  - Source: SerpAPI account dashboard
  - How to set:
    - Sign in to [https://serpapi.com](https://serpapi.com)
    - Copy your API key from dashboard
    - Paste it as `SERP_API_KEY=...`
- `ASTRA_DB_API_ENDPOINT`
  - Source: DataStax Astra DB database settings
  - How to set:
    - Create/select an Astra DB database
    - Copy the API endpoint URL
    - Paste it as `ASTRA_DB_API_ENDPOINT=...`
- `ASTRA_DB_APPLICATION_TOKEN`
  - Source: DataStax Astra DB application tokens
  - How to set:
    - Create an application token with required access
    - Paste it as `ASTRA_DB_APPLICATION_TOKEN=...`
- `GOOGLE_CLIENT_ID`
  - Source: Google Cloud Console OAuth credentials
  - How to set:
    - Create OAuth client credentials
    - Copy the OAuth client ID
    - Paste it as `GOOGLE_CLIENT_ID=...`
- `JWT_SECRET`
  - Source: generated locally by you
  - How to set:
    - Generate a long random string (at least 32+ chars)
    - Example PowerShell:
      ```powershell
      [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
      ```
    - Paste the output as `JWT_SECRET=...`
- `PRODUCT_HUNT_TOKEN` (optional)
  - Source: Product Hunt API dashboard
  - What it's for: one of two discovery sources for the competitor worker
    (the other, Hacker News "Show HN", needs no key at all). Leave unset and
    the worker runs on Hacker News alone — it degrades silently, it does not
    fail.
  - How to set:
    - Sign in to your Product Hunt account
    - Go to [api.producthunt.com/v2/oauth/applications](https://api.producthunt.com/v2/oauth/applications)
    - Click "Add an application" (any name/redirect URL works — you're only
      after the token, not doing a real OAuth flow)
    - Copy the generated `developer_token` (it does not expire)
    - Paste it as `PRODUCT_HUNT_TOKEN=...`
  - Cost: free. No paid tier gate on this token — Product Hunt's own limits
    are a query-complexity cap of 1000 and a rate limit that resets every 15
    minutes, both far above what this worker uses per report.

### First-time `.env` template

Create `stratos-backend/.env` like this and replace values:

```env
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/stratos

GROQ_API_KEY_ALISHA=<your_groq_api_key_1>
GROQ_API_KEY_ENCRIL=<your_groq_api_key_2>
SERP_API_KEY=<your_serpapi_key>

ASTRA_DB_API_ENDPOINT=<your_astra_api_endpoint>
ASTRA_DB_APPLICATION_TOKEN=<your_astra_application_token>

GOOGLE_CLIENT_ID=<your_google_oauth_client_id>
JWT_SECRET=<your_strong_random_secret>

# Optional — competitor worker falls back to Hacker News alone if unset
PRODUCT_HUNT_TOKEN=<your_product_hunt_developer_token>
```

### Security note for first-time setup

- Never commit `.env` to git.
- If any keys were shared or committed accidentally, rotate them immediately in the provider dashboard.

## 4) Astra DB Collection Setup (First Time)

Run the two provisioning scripts against your Astra DB — **do not create
collections by hand in the Astra UI**. This section used to instruct manual
creation of 4 collections and omitted a 5th (`evidence_bundles`); that's
exactly how a real environment ended up missing it while running for weeks.
The scripts are the single source of truth for what collections must exist
and how, so they can't drift from this doc again.

```powershell
cd stratos-backend
.\venv\Scripts\Activate.ps1
python scripts\create_astra_collections.py    # the 4 plain document collections
python scripts\ensure_astra_collections.py    # the 1 vector collection (embeddings)
```

Both are idempotent — safe to re-run any time, including against a database
that already has some or all of the collections.

| Collection | Type | Purpose | Created by |
| --- | --- | --- | --- |
| `evidence` | Standard | Per-source archive: raw scraped page text + metadata | `create_astra_collections.py` |
| `trend_items` | Standard | News / papers / social trend items | `create_astra_collections.py` |
| `competitor_insights` | Standard | Structured, profiled competitor memory | `create_astra_collections.py` |
| `evidence_bundles` | Standard | Per-section pre-ranked evidence cache | `create_astra_collections.py` |
| `embeddings` | **Vector** (server-side `$vectorize`, provider `nvidia`, model `NV-Embed-QA`, 1024-dim, cosine) | Chunked, vectorized evidence for hybrid (lexical + semantic) ranking | `ensure_astra_collections.py` |

Only `embeddings` is vector-enabled, and its config is fixed by the model
Astra calls server-side — there is no dimension/metric to choose manually,
and no local embedding model to install (no `sentence-transformers`, no
`torch`). See `app/services/embedding_service.py` for why this provider was
picked.

### Verify

```powershell
python -c "from astrapy import DataAPIClient; from app.config import settings; c=DataAPIClient(settings.ASTRA_DB_APPLICATION_TOKEN); kw={'keyspace': settings.ASTRA_DB_KEYSPACE} if settings.ASTRA_DB_KEYSPACE else {}; db=c.get_database_by_api_endpoint(settings.ASTRA_DB_ENDPOINT, **kw); print(sorted(x.name for x in db.list_collections()))"
```
Expect all 5 names listed above.

### Astra setup checklist

- [ ] `create_astra_collections.py` run — `evidence`, `trend_items`, `competitor_insights`, `evidence_bundles` all report created or already-exists
- [ ] `ensure_astra_collections.py` run — `embeddings` reports created or already-configured for `nvidia`/`NV-Embed-QA`
- [ ] Verify script above lists all 5 collections

## 5) Start Infrastructure

1. Start PostgreSQL
2. Create a database named `stratos`
3. Start Redis

### Verify Redis is running (Windows)

Start Redis service:

```cmd
sc start Redis
```

Then check status:

Run:

```cmd
sc query Redis
```

Expected status should include:

```text
STATE              : 4  RUNNING
```

Optional connectivity check:

```cmd
redis-cli ping
```

Expected:

```text
PONG
```

## 6) Initialize Database Tables

From `stratos-backend`:

```powershell
python scripts/create_tables.py
```

On a database that existed before the competitor worker (i.e. anywhere this
repo was set up earlier), also run the one-time column patch — safe to
re-run, and a no-op on a fresh database where `create_tables.py` already
created the columns:

```powershell
python scripts/add_competitor_columns.py
```

## 7) Run the Backend API

From `stratos-backend`:

```powershell
uvicorn app.main:app --reload
```

Health check:

- Open `http://127.0.0.1:8000/`
- Expected response:

```json
{"status":"ok","service":"stratos-backend"}
```

### View SSE events

Use this endpoint (single slash):

```text
http://127.0.0.1:8000/stream/events
```

Ways to view:

- Browser: open the URL directly
- Swagger: `http://127.0.0.1:8000/docs` -> `GET /stream/events`
- Terminal (recommended):

```powershell
curl -N http://127.0.0.1:8000/stream/events
```

If nothing appears immediately, trigger a flow like `start-session`; events are streamed only when they are published.

## 8) Run Celery Worker (Separate Terminal)

From `stratos-backend`:

```powershell
& "..\venv\Scripts\Activate.ps1"
celery -A app.workers.celery_app worker --loglevel=info --pool=threads --concurrency=8 -Q celery,heavy_llm
```

Note: `--pool=threads` (2026-09-14 remediation Phase 4.1, replacing the
earlier `--pool=solo` recommendation) works identically on Windows, Linux,
and macOS -- unlike `--pool=prefork` (Celery's own default), which needs
`os.fork()` and is unavailable on Windows. `--pool=solo` was a
single-threaded Windows workaround; this pipeline's fan-out (research/
trend/competitor running in parallel, all 7 sections dispatched as
separate tasks) was always written to run concurrently, `--pool=solo`
just serialized it back down to one task at a time regardless of platform.
`-Q celery,heavy_llm` listens on both queues -- section_writer/verdict/
outline route to `heavy_llm` (Phase 3.3.g), and omitting either queue name
means tasks routed to it are enqueued but never picked up by this worker.

On startup, look for `app.workers.competitor_worker.run_competitor` (and the
other pipeline stages) in Celery's registered-tasks banner to confirm every
worker loaded. `celery_app.py` tolerates a genuinely missing module (logs and
continues) so a typo or partial checkout fails quietly — check the banner if
a stage never fires.

## Quick Run Checklist

- [ ] Python virtual environment created
- [ ] Dependencies installed
- [ ] `.env` configured
- [ ] PostgreSQL running and `stratos` DB created
- [ ] Redis running
- [ ] Tables created via script
- [ ] API running on port 8000
- [ ] Celery worker running

