# 06 — External Dependencies & Costs

> Every third-party service Stratos relies on: what it does, how to sign up, which plan to pick, and what it costs. Prices are approximate as of mid-2026 — always confirm on the provider's pricing page before committing a card.

## 1. Summary table

| # | Service | Role | Free tier enough for launch? | Expected cost at ~100 reports/month |
|---|---------|------|------------------------------|--------------------------------------|
| 1 | **Groq** | LLM for clarification, outline, query-gen, section writing | Yes (rate-limited) | $0–15 |
| 2 | **SerpAPI** | Google search/news/patents results for research worker | 100 searches/month free — **NOT enough** | ~$75 (5k searches plan) — see cheaper alternatives §3 |
| 3 | **DataStax Astra DB** | Evidence/trend document store (+ future vectors) | Yes (generous free tier) | $0 |
| 4 | **Neon** (or Supabase) | Managed Postgres | Yes | $0–19 |
| 5 | **Redis** (Railway plugin / Render Redis / Upstash TCP) | Celery broker + pub/sub | Small instance | $5–10 |
| 6 | **Railway** or **Render** | Hosts API + Celery workers (Docker) | Trial credits only | $10–25 |
| 7 | **Vercel** | Hosts Next.js frontend | Yes (Hobby) | $0 (upgrade to Pro $20 when commercial — check ToS: Hobby prohibits commercial use) |
| 8 | **Cloudflare R2** | PDF/object storage | Yes (10 GB free, zero egress fees) | $0 |
| 9 | **Google Cloud Console** | OAuth client for Google Sign-In | Free | $0 |
| 10 | **Stripe** (global) / **Razorpay** (India) | Payments | Pay per transaction | 2.9% + 30¢ / ~2% |
| 11 | **Sentry** | Error monitoring | Yes (5k events/mo) | $0 |
| 12 | **Domain** (Namecheap/Cloudflare/GoDaddy) | yourdomain.com | — | $10–15/year |
| 13 | **Resend** (or Postmark) | Transactional email (receipts, report-ready) — optional at launch | Yes (3k emails/mo) | $0 |
| 14 | Free data feeds: HN Algolia, GDELT, Google News RSS, arXiv | Trend worker sources | Free, no keys | $0 |

**Realistic monthly burn at launch: $20–50/month + domain.** The dominant variable cost is SerpAPI.

## 2. Per-service setup instructions

### 2.1 Groq (LLM)

1. Go to `console.groq.com` → sign up with Google/GitHub.
2. Left sidebar → **API Keys** → **Create API Key** → name it `stratos-prod` → copy the key immediately (it is shown once).
3. Put it in env as `GROQ_API_KEY`, and set `LLM_PROVIDER=groq`.
4. Model used: `llama-3.1-8b-instant` (hardcoded in `app/llm/client_groq.py`). If Groq retires this model, pick the closest small Llama instant model from their model list and update that one file.
5. **Watch out:** free-tier rate limits (requests/min and tokens/min). A single report makes ~15–30 LLM calls. If you hit 429s during section writing, either add retry-with-backoff (already partially present via Celery retries) or move to the paid dev tier (pay-as-you-go, cents per report).

### 2.2 SerpAPI (search results)

1. `serpapi.com` → register → dashboard shows **Your Private API Key** → env `SERP_API_KEY`.
2. Free plan: 100 searches/month. Each report uses ~6–12 searches (web + news + patents fan-out) → free tier covers ~10 reports. Fine for development, **not for launch**.
3. Paid: ~$75/mo for 5,000 searches. Before paying, consider cheaper drop-in alternatives and abstract the provider behind `research_service.py`:
   - **Serper.dev** — ~$1–2 per 1,000 queries (credits), Google results, trivially similar JSON.
   - **Brave Search API** — free tier 2,000 queries/mo, paid from $5/1k.
   - **Tavily** — search API built for AI agents, generous free tier.
   Swapping providers touches exactly one file (`app/services/research_service.py`) — this is a recommended cost optimization once traction is proven, not a launch blocker.

### 2.3 DataStax Astra DB

1. `astra.datastax.com` → sign up → **Create Database** → Serverless (Vector), name `stratos`, pick a region close to your backend host (e.g. `us-east-2` if backend is US).
2. After the DB is Active: **Connect** tab → copy the **API Endpoint** → env `ASTRA_DB_API_ENDPOINT`.
3. **Generate Token** (role: Database Administrator) → env `ASTRA_DB_APPLICATION_TOKEN`.
4. No schema setup needed — the code creates/uses collections (`evidence`, `evidence_bundles`, `trend_items`, `competitor_insights`) on the fly.
5. The backend is fail-soft: if these env vars are missing everything still works via Postgres fallbacks (slightly worse section quality). This makes Astra a **non-blocking** dependency.

### 2.4 Neon (Postgres)

1. `neon.tech` → sign up → **Create project** `stratos` → pick region matching your backend host.
2. Copy the **connection string** (pooled) → env `DATABASE_URL`. It looks like `postgresql://user:pass@ep-xxx.aws.neon.tech/neondb?sslmode=require`.
3. Free tier: 0.5 GB storage, auto-suspend — fine for launch. (Alternative: Supabase, same idea; or Railway's Postgres plugin to keep everything on one platform.)
4. Run migrations against it: `DATABASE_URL=... alembic upgrade head` (doc 07 §4.3).

### 2.5 Redis

Requirements: standard Redis protocol (TCP), two logical DBs (0 = Celery, 1 = pub/sub), persistent connection support for pub/sub.

- **Simplest:** if backend is on Railway → add the **Redis plugin** to the project; env var `REDIS_URL` is injected. Set `REDIS_BROKER_URL=${REDIS_URL}/0` and `REDIS_PUBSUB_URL=${REDIS_URL}/1`.
- On Render → create a **Render Key Value** (Redis-compatible) instance.
- Upstash works but choose the **TCP/native** connection (not the REST API) because Celery and pub/sub need real Redis protocol.
- Cost: $5–10/month for the smallest persistent instance.

### 2.6 Railway (backend hosting — or Render, equivalent)

1. `railway.app` → sign in with GitHub → **New Project** → **Deploy from GitHub repo** → select the repo.
2. Full click-by-click deploy steps are in doc 07 §5. Cost model: usage-based, expect $10–20/month for one API service + one worker service + Redis.
3. Render equivalent: two **Web Service**/**Background Worker** services from the same Dockerfile; free instances spin down (bad for SSE and Celery) so use the $7/mo starter instances.

### 2.7 Vercel (frontend)

1. `vercel.com` → sign in with GitHub → **Add New Project** → import the repo → set **Root Directory** = `stratos-frontend`.
2. Framework auto-detected (Next.js). Env vars in doc 07 §6.
3. Hobby tier is free but **non-commercial**; upgrade to Pro ($20/mo) once you charge users.

### 2.8 Cloudflare R2 (PDF storage)

1. `dash.cloudflare.com` → sign up → **R2 Object Storage** → **Create bucket** `stratos-exports` (keep it private).
2. **Manage R2 API Tokens** → create token with Object Read & Write on that bucket → copy **Access Key ID** and **Secret Access Key** → env `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`; your **Account ID** (dashboard sidebar) → `R2_ACCOUNT_ID`; set `R2_BUCKET=stratos-exports`, `EXPORT_STORAGE=r2`.
3. Free: 10 GB storage, 1M writes/mo, **zero egress fees** (why we pick R2 over S3).

### 2.9 Google OAuth

1. `console.cloud.google.com` → create project `stratos` → **APIs & Services → OAuth consent screen**: External, app name Stratos, your support email; scopes: just `openid email profile`; publish the app (stays in "testing" = only allow-listed emails, fine for beta; "in production" needs nothing extra for these basic scopes).
2. **Credentials → Create Credentials → OAuth client ID** → Web application:
   - Authorized JavaScript origins: `http://localhost:3000` and later `https://yourdomain.com`.
   - No redirect URI needed for the Google Identity Services popup flow.
3. Copy the **Client ID** → backend env `GOOGLE_CLIENT_ID` and frontend env `NEXT_PUBLIC_GOOGLE_CLIENT_ID` (same value).

### 2.10 Payments — Stripe or Razorpay

Decision rule: **selling globally → Stripe; selling primarily to Indian customers with an Indian entity → Razorpay** (UPI support matters enormously in India). Full integration steps in doc 08 §3; India-specific notes in doc 10 §6.

### 2.11 Sentry

1. `sentry.io` → new project ×2 (Python/FastAPI, Next.js) → copy both DSNs → env `SENTRY_DSN` (backend) and `NEXT_PUBLIC_SENTRY_DSN` (frontend).

### 2.12 Domain

1. Buy `getstratos.io` / `stratos.app` / whatever is free (~$10–15/yr) at Cloudflare Registrar (at-cost pricing) or Namecheap.
2. DNS: apex/`www` → Vercel (they show you the exact A/CNAME records), `api.yourdomain.com` → CNAME to the Railway/Render service domain. Both platforms auto-issue TLS certificates.

## 3. Cost model per report (unit economics)

| Component | Per-report cost |
|---|---|
| Groq LLM (~25 calls, small model) | $0.01–0.05 |
| SerpAPI (10 searches @ $75/5k) | $0.15 (or ~$0.01–0.02 via Serper/Brave) |
| Trend feeds | $0 |
| Astra/Neon/R2 | ~$0 marginal |
| **Total marginal cost** | **≈ $0.05–0.20 per report** |

At $19/month for 10 reports (doc 08 pricing), gross margin is >90%. The business works; the risk is acquisition, not unit economics.

## 4. Key management rules

1. One key per environment (`stratos-dev`, `stratos-prod`) — revoking dev keys must never break prod.
2. Keys live in: local `.env` (gitignored) and platform secret managers. Nowhere else. Never in code, never in the repo, never in screenshots.
3. If a key leaks (e.g. accidentally committed): revoke it at the provider **first**, then rewrite git history or rotate and move on.
4. Set billing alerts: Groq/SerpAPI dashboards + a calendar reminder to check spend weekly for the first month.
