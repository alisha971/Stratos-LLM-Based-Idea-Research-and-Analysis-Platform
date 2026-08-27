# 03 — Environment Variables & API Keys

> Every secret/config value the fast-ship build reads, **where to get it**, and
> **where to put it**. Nothing here is hard-coded — the app reads it all from
> environment variables. Placeholders live in `stratos-backend/.env.example` and
> `stratos-frontend/.env.example`; copy those and fill in real values.
>
> **Golden rule:** real values go in `.env` (backend) / `.env.local` (frontend)
> locally — both are gitignored — and in the hosting platform's secret manager
> in production. Never commit a real key.

---

## Quick start (local)

```bash
# Backend
cd stratos-backend
cp .env.example .env          # then edit .env with the values below
docker compose up -d          # postgres + redis
python scripts/create_tables.py

# Frontend
cd ../stratos-frontend
cp .env.example .env.local    # then edit .env.local
```

For local dev you can skip Google OAuth entirely: set `DEV_AUTH_BYPASS=true` in
the backend `.env`, leave `NEXT_PUBLIC_GOOGLE_CLIENT_ID` empty, and use the
**"Continue in dev mode"** button on `/login` (it authenticates as `dev-user`
via the literal `dev` token). This bypass is force-disabled in production.

---

## Backend keys — file: `stratos-backend/.env`

| Variable | Required? | What it is / where to get it |
|---|---|---|
| `ENV` | Yes | `development` locally, `production` on the server. Production turns on the boot-time safety guards below. |
| `DATABASE_URL` | Yes | Postgres connection string. **Local:** the docker-compose default `postgresql://stratos:stratos@localhost:5432/stratos`. **Prod:** create a free Postgres at [neon.tech](https://neon.tech) → copy its connection string. |
| `REDIS_BROKER_URL` | Yes | Celery broker. **Local:** `redis://localhost:6379/0` (docker-compose). **Prod:** Railway Redis plugin URL, append `/0`. |
| `REDIS_PUBSUB_URL` | Yes | SSE pub/sub (a *different* Redis DB number). **Local:** `redis://localhost:6379/1`. **Prod:** same Railway Redis URL, append `/1`. |
| `GROQ_API_KEY_1` | Yes | LLM inference. Get it free at [console.groq.com/keys](https://console.groq.com/keys). Powers clarification, outline, research queries, and section writing. |
| `GROQ_API_KEY_2` | Yes | A second Groq key on a *separate* account. `app/llm/client.py` uses the two as a fallback pool — one primary, the other on rate-limit/API failure — roughly doubling the effective daily token quota. (The code still reads these as `GROQ_API_KEY_ALISHA` / `GROQ_API_KEY_ENCRIL`; rename pending.) |
| `SERP_API_KEY` | Yes | Web search for the research worker. Sign up at [serpapi.com](https://serpapi.com) → API key (free tier ~100 searches/mo). |
| `ASTRA_DB_API_ENDPOINT` | Yes | Vector evidence store. Create a free DB at [astra.datastax.com](https://astra.datastax.com) → "API Endpoint" on the DB dashboard. |
| `ASTRA_DB_APPLICATION_TOKEN` | Yes | Same Astra DB → "Generate Token" (role: DB Admin). Starts with `AstraCS:`. |
| `ASTRA_DB_KEYSPACE` | Optional | Astra keyspace; default `default_keyspace` is fine. |
| `JWT_SECRET` | Yes (prod) | Signs app login tokens. Generate with `openssl rand -hex 32` (64 hex chars). **The app refuses to boot in production if this is still `supersecret`.** |
| `GOOGLE_CLIENT_ID` | Yes for real login | Google OAuth client id. See [Google OAuth setup](#google-oauth-setup) below. Used to verify the Google ID token on `/auth/google`. |
| `DEV_AUTH_BYPASS` | Dev only | `true` locally to enable the `dev` token. **Must be `false`/absent in production** — the app refuses to boot if it's `true` while `ENV=production`. |
| `FRONTEND_ORIGIN` | Yes | Exact origin allowed by CORS. **Local:** `http://localhost:3000`. **Prod:** your Vercel/frontend URL (e.g. `https://stratos.yourdomain.com`), no trailing slash. |
| `EXPORT_STORAGE` | Yes | `local` for fast-ship (PDFs served from disk). `r2` only after the premium object-storage task. |
| `EXPORT_DIR` | Optional | Where PDFs are written; default `exports`. In prod mount a Railway volume here so PDFs survive restarts. |
| `START_SESSION_RATE` | Optional | Per-user start-session limit; default `5/hour`. |
| `CLARIFICATION_CHAT_RATE` | Optional | Per-user chat limit; default `60/hour`. |
| `GLOBAL_DAILY_SESSION_CAP` | Optional | Wallet seatbelt — total sessions/day across all users; default `100`. 503 past it. |
| `MAX_TEXT_LENGTH` | Optional | Max chars for idea/message input; default `2000`. |

### Not needed for fast-ship (premium only)
`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`
(Cloudflare R2 object storage), and `SENTRY_DSN`. Leave unset — `EXPORT_STORAGE=local`
means no R2 is used.

---

## Frontend keys — file: `stratos-frontend/.env.local`

| Variable | Required? | What it is / where to get it |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Yes | Backend base URL, no trailing slash. **Local:** `http://localhost:8000`. **Prod:** `https://api.yourdomain.com`. |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Yes for real login | The **same** OAuth client id as the backend's `GOOGLE_CLIENT_ID`. Leave empty locally to use the dev-mode button. |

> `NEXT_PUBLIC_*` vars are baked into the client bundle at build time and are
> **public** — never put a secret here. The Google *client id* is public by
> design; the Google *client secret* is not used by this app at all.

---

## Google OAuth setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create/select a project.
2. **APIs & Services → OAuth consent screen** → External → fill app name, support email; add your email as a test user.
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID → Web application.**
4. **Authorized JavaScript origins:**
   - `http://localhost:3000` (local)
   - `https://stratos.yourdomain.com` (prod frontend)
5. Copy the **Client ID** (looks like `1234-abc.apps.googleusercontent.com`) into:
   - backend `.env` → `GOOGLE_CLIENT_ID`
   - frontend `.env.local` → `NEXT_PUBLIC_GOOGLE_CLIENT_ID`

(No redirect URIs or client secret needed — this app uses Google Identity
Services in-page and verifies the ID token server-side.)

---

## Where secrets live in production

| Platform | What goes there |
|---|---|
| **Railway** (backend, single service running API + worker) | All backend `.env` values as service variables. Mount a volume at `/app/exports`. |
| **Neon** | Provides `DATABASE_URL`. |
| **Railway Redis** | Provides the base URL for `REDIS_BROKER_URL` (`/0`) and `REDIS_PUBSUB_URL` (`/1`). |
| **Vercel** (frontend) | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`. |
| **Groq / SerpAPI / DataStax / Google Cloud** | Where you generate the keys above. |

---

## Pre-flight checklist

- [ ] `git check-ignore stratos-backend/.env` prints the path (i.e. it IS ignored).
- [ ] Backend boots: `uvicorn app.main:app` → `GET /healthz` returns `{"ok": true}`.
- [ ] `python scripts/run_pipeline_smoke.py` prints `PASS` (uses the `dev` token locally).
- [ ] Production: `ENV=production` with a real 64-char `JWT_SECRET` and `DEV_AUTH_BYPASS` unset — app boots; with either misconfigured, it refuses to start (that's the safety guard working).
