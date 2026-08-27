---
name: stratos-deploy
description: Deploy or troubleshoot Stratos in production — Railway (API + Celery worker), Vercel (Next.js frontend), Neon Postgres, Redis, Cloudflare R2, env vars, domains, OAuth origins. Use when deploying, redeploying, changing production env vars, or debugging production-only failures.
disable-model-invocation: true
---

# Stratos Deploy

Compressed operational reference. Click-by-click first-time setup: `stratos-launch-plan/07-DEPLOYMENT-GUIDE.md`. Fast-ship single-container variant: `stratos-mvp-fastship/01-MVP-IMPLEMENTATION-PLAN.md` §3.

## Topology (premium)

- **Vercel**: frontend, root dir `stratos-frontend`. Env: `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, `NEXT_PUBLIC_SENTRY_DSN`. Env changes require a redeploy.
- **Railway service 1 (API)**: root `stratos-backend`, Dockerfile build, port 8000, healthcheck `/healthz`.
- **Railway service 2 (worker)**: same repo/image, start command `celery -A app.workers.celery_app worker --loglevel=info --concurrency=4`. **Same env vars as API** (use project-level shared variables).
- **Railway Redis plugin**: `REDIS_BROKER_URL=${{Redis.REDIS_URL}}/0`, `REDIS_PUBSUB_URL=${{Redis.REDIS_URL}}/1`.
- Neon (migrations run from local: `$env:DATABASE_URL="<neon>"; alembic upgrade head`), Astra (optional/fail-soft), R2 (`EXPORT_STORAGE=r2`).
- Fast-ship variant instead: ONE Railway service running `start.sh` (uvicorn + celery in one container) + a volume at `/app/exports`, `EXPORT_STORAGE=local`, no R2.

## Pre-deploy gates

1. CI green; smoke script passes locally.
2. Secret grep clean; `.env` not in the commit.
3. Contract doc, backend, frontend all in the same deploy window if the API surface changed (breaking changes are coordinated, no /v1 versioning).
4. Production env refuses default `JWT_SECRET` and `DEV_AUTH_BYPASS` — expect boot failure if misconfigured (that's correct behavior).

## Post-deploy verification

Run `07-DEPLOYMENT-GUIDE.md` Part 7 in incognito: login → idea → consent → live progress → report → PDF download → refresh-resume. Then check worker logs and Sentry.

## Production-only failure map

| Symptom | Fix location |
|---|---|
| Google sign-in popup fails | OAuth client "Authorized JavaScript origins" must include the exact prod domain; `NEXT_PUBLIC_GOOGLE_CLIENT_ID` matches backend `GOOGLE_CLIENT_ID` |
| CORS errors in console | Railway `FRONTEND_ORIGIN` exact match (scheme + host, no trailing slash) |
| Session starts, nothing happens | Worker service down or broker URL mismatch — check worker service logs for the Celery banner |
| Research stalls | SerpAPI quota/key (dashboard) |
| Sections 429 | Groq rate limits — wait or upgrade tier |
| PDF 404 | R2 vars present on BOTH services; `EXPORT_STORAGE` consistent |
| SSE never connects | Network tab: `/stream/events/...` with token param; API service logs |

## Rollback

Railway: Deployments → previous good → Redeploy. Vercel: Deployments → Promote to Production. DB: migrations are forward-only in practice — write a new corrective migration rather than downgrading.
