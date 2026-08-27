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
- `GROQ_API_KEY_1`
- `GROQ_API_KEY_2`
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
- `GROQ_API_KEY_1` / `GROQ_API_KEY_2`
  - Source: Groq Console API keys — two separate keys/accounts
  - What it's for: `app/llm/client.py` routes each LLM call to one key as
    primary and falls back to the other on failure (rate limit, API error),
    roughly doubling the effective daily token quota. Both keys use the same
    model (`openai/gpt-oss-20b`).
  - How to set:
    - Sign in to [https://console.groq.com](https://console.groq.com) with
      each account
    - Create an API key in each
    - Paste them as `GROQ_API_KEY_1=...` and `GROQ_API_KEY_2=...`
  - Note: the code currently still reads these as `GROQ_API_KEY_ALISHA` /
    `GROQ_API_KEY_ENCRIL` (`app/config.py`, `app/llm/client_groq.py`); a rename
    to `_1`/`_2` is pending. Until then, use the `_ALISHA`/`_ENCRIL` names in
    your local `.env`.
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

GROQ_API_KEY_1=<your_groq_api_key_1>
GROQ_API_KEY_2=<your_groq_api_key_2>
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

Create these 4 collections in Astra DB Data Explorer (same keyspace for all, recommended keyspace: `stratos`).

| Collection | Type | Purpose |
| --- | --- | --- |
| `embeddings` | Vector-enabled | RAG / semantic search |
| `evidence` | Standard collection | Raw scraped evidence |
| `trend_items` | Standard collection | News / papers / social trends |
| `competitor_insights` | Standard collection | Competitor analysis |

### Most important rule

Only `embeddings` should be vector-enabled.

### Create `embeddings` (vector-enabled)

Use these exact settings:

- Collection Name: `embeddings`
- Vector-enabled collection: `ON`
- Embedding generation method: `Bring my own embeddings`
- Dimensions: `384`
- Similarity metric: `Cosine`

Do not choose automatic/provider-generated embeddings here if you plan to generate vectors in your own backend embedding worker.

### Create `evidence` (standard)

- Collection Name: `evidence`
- Vector-enabled collection: `OFF`

### Create `trend_items` (standard)

- Collection Name: `trend_items`
- Vector-enabled collection: `OFF`

### Create `competitor_insights` (standard)

- Collection Name: `competitor_insights`
- Vector-enabled collection: `OFF`

### Why this setup

- `embeddings` handles vector retrieval.
- `evidence` stores ground-truth scraped content.
- `trend_items` stores trend intelligence.
- `competitor_insights` stores structured competitor memory.

### Embedding model recommendation (for backend worker)

Recommended lightweight model:

```text
sentence-transformers/all-MiniLM-L6-v2
```

This model outputs 384-dimensional vectors, so Astra dimensions must be `384`.

If needed later, install:

```text
sentence-transformers
torch
```

### Astra setup checklist

- [ ] `embeddings` created (vector-enabled, 384 dims, cosine)
- [ ] `evidence` created (standard)
- [ ] `trend_items` created (standard)
- [ ] `competitor_insights` created (standard)

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
celery -A app.worker.celery_app worker --loglevel=info --pool=solo
```

Note: `--pool=solo` is recommended on Windows.

## Known Blocker

`app/workers/celery_app.py` currently imports several worker modules that are not present in this repository (`trend_worker`, `competitor_worker`, `section_worker`, `embedding_worker`, `assembler_worker`, `export_worker`).

If these files are still missing, Celery startup can fail.

Possible resolutions:

- Comment out missing imports in `app/workers/celery_app.py` for now, or
- Add the missing worker modules before running Celery

## Quick Run Checklist

- [ ] Python virtual environment created
- [ ] Dependencies installed
- [ ] `.env` configured
- [ ] PostgreSQL running and `stratos` DB created
- [ ] Redis running
- [ ] Tables created via script
- [ ] API running on port 8000
- [ ] Celery worker running

