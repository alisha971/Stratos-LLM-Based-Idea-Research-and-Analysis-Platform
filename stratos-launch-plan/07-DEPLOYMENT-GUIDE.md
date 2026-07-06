# 07 — Deployment Guide (Click-by-Click)

> Written so a person who has never deployed anything can follow it. Do things **in this exact order**. Prerequisites: the code work in docs 03 and 04 is done (at minimum phases B1–B7 and F1–F3), and you completed the sign-ups in doc 06 (Groq, SerpAPI, Astra, Neon, Cloudflare R2, Google OAuth, Sentry, a domain, GitHub account).
>
> Time needed: ~2–3 hours the first time. Nothing here is dangerous; everything is undoable.

---

## Part 1 — Verify everything works locally first

Never deploy code that doesn't run on your machine.

1. Open a terminal in `stratos-backend/`.
2. Start the databases: `docker compose up -d` (needs Docker Desktop installed and running; download from `docker.com/products/docker-desktop`, install with default options, restart your computer if it asks).
3. Create/activate the Python environment and install:
   - Windows PowerShell: `python -m venv venv; .\venv\Scripts\Activate.ps1; pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in every value (your Groq key, SerpAPI key, `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/stratos` for the compose DB, etc.). Set `ENV=development` and `DEV_AUTH_BYPASS=true`.
5. Apply the schema: `alembic upgrade head`.
6. Start three processes in three terminals (all with the venv activated):
   - Terminal A: `uvicorn app.main:app --reload`
   - Terminal B: `celery -A app.workers.celery_app worker --loglevel=info --pool=solo` (`--pool=solo` is needed on Windows)
   - Terminal C (frontend): in `stratos-frontend/`, `npm install` then copy `.env.example` → `.env.local`, then `npm run dev`
7. Run the smoke test: `python scripts/run_pipeline_smoke.py` in a fourth terminal. It must print `PASS` and you must be able to open the generated PDF.
8. Also do it by hand once: open `http://localhost:3000`, sign in, type an idea, answer the questions, approve, wait, read the report, download the PDF.

**Do not continue until step 7 and 8 both work.**

---

## Part 2 — Push the code to GitHub

1. Create a GitHub account at `github.com` if you don't have one.
2. Click the **+** (top right) → **New repository** → name `stratos` → **Private** → Create.
3. In your project folder (`c:\...\stratos`), make sure `.gitignore` excludes `.env`, `.env.local`, `venv/`, `node_modules/`, `exports/`. Open each `.gitignore` and check.
4. In a terminal at the project root:

```bash
git add -A
git status   # LOOK at this list. If you see .env or any file with keys, STOP and fix .gitignore first.
git commit -m "Production-ready Stratos"
git remote add origin https://github.com/YOURUSERNAME/stratos.git
git push -u origin main
```

---

## Part 3 — Create the production databases

### 3.1 Neon Postgres

1. `neon.tech` → your `stratos` project → **Dashboard** → copy the **pooled connection string**.
2. On your local machine, apply migrations to the production DB (one-time):
   - PowerShell: `$env:DATABASE_URL="<the neon string>"; alembic upgrade head`
3. Confirm: in the Neon console → **Tables** — you should see `users`, `sessions`, `reports`, etc.

### 3.2 Astra DB and R2

Nothing to do beyond the sign-up steps in doc 06 §2.3 and §2.8 — the app creates its collections and objects itself. Just have the 5 values ready: `ASTRA_DB_API_ENDPOINT`, `ASTRA_DB_APPLICATION_TOKEN`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.

---

## Part 4 — Deploy the backend to Railway

(Render works the same way; Railway shown because it bundles Redis nicely.)

### 4.1 Create the project and Redis

1. `railway.app` → **Login with GitHub** → **New Project** → **Deploy from GitHub repo** → pick your `stratos` repo. It will create one service; we'll configure it as the API.
2. In the project canvas, click **+ Create** → **Database** → **Add Redis**. Wait until it's green.

### 4.2 Configure the API service

1. Click the service Railway created from your repo → **Settings**:
   - **Root Directory:** `stratos-backend`
   - **Builder:** Dockerfile (it auto-detects `stratos-backend/Dockerfile`)
   - **Networking → Generate Domain** → note the URL (like `stratos-api-production.up.railway.app`). Set the port to `8000` if asked.
   - **Healthcheck path:** `/healthz`
2. **Variables** tab → **Raw editor** → paste (replace values):

```
ENV=production
DATABASE_URL=<neon pooled connection string>
REDIS_BROKER_URL=${{Redis.REDIS_URL}}/0
REDIS_PUBSUB_URL=${{Redis.REDIS_URL}}/1
GROQ_API_KEY=<yours>
LLM_PROVIDER=groq
SERP_API_KEY=<yours>
ASTRA_DB_API_ENDPOINT=<yours>
ASTRA_DB_APPLICATION_TOKEN=<yours>
GOOGLE_CLIENT_ID=<yours>.apps.googleusercontent.com
JWT_SECRET=<paste 64 random characters from a password generator>
EXPORT_STORAGE=r2
R2_ACCOUNT_ID=<yours>
R2_ACCESS_KEY_ID=<yours>
R2_SECRET_ACCESS_KEY=<yours>
R2_BUCKET=stratos-exports
FRONTEND_ORIGIN=https://yourdomain.com
SENTRY_DSN=<backend DSN>
```

(`${{Redis.REDIS_URL}}` is Railway's variable-reference syntax — it wires in the Redis you created. If your Redis service has a different name, use that name.)
3. Click **Deploy**. Watch the build logs until "Deployment successful".
4. Test: open `https://<your-api-domain>/healthz` in a browser → `{"ok": true}`.

### 4.3 Create the worker service (same image, different command)

1. In the same project: **+ Create** → **GitHub Repo** → same repo again.
2. Its **Settings**: Root Directory `stratos-backend`, Dockerfile builder, and set **Custom Start Command** = `celery -A app.workers.celery_app worker --loglevel=info --concurrency=4`. No public domain needed.
3. **Variables**: same set as the API service (Railway lets you use **Shared Variables** at the project level — do that so you maintain one copy).
4. Deploy; logs should show Celery's banner and `celery@... ready.`

---

## Part 5 — Deploy the frontend to Vercel

1. `vercel.com` → **Login with GitHub** → **Add New… → Project** → import `stratos`.
2. **Root Directory:** click Edit → select `stratos-frontend`.
3. **Environment Variables:**

```
NEXT_PUBLIC_API_BASE_URL=https://<your railway api domain>
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<same client id as backend>
NEXT_PUBLIC_SENTRY_DSN=<frontend DSN>
```

4. Click **Deploy**. In ~2 minutes you get `https://stratos-xxx.vercel.app`.
5. Smoke check: open it → landing page loads → sign in with Google (it will fail until Part 6 step 3, because Google only allows listed origins — that's expected).

---

## Part 6 — Domain + final wiring

1. **Frontend domain:** Vercel project → **Settings → Domains** → add `yourdomain.com` and `www.yourdomain.com` → follow the DNS instructions shown (add the A/CNAME records at your registrar). Wait for the green checkmark (minutes to an hour).
2. **API domain (optional but nice):** Railway API service → Settings → **Custom Domain** → `api.yourdomain.com` → add the CNAME at your registrar. Then update Vercel's `NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com` and **redeploy the frontend** (env changes need a redeploy).
3. **Google OAuth origins:** `console.cloud.google.com` → Credentials → your OAuth client → add `https://yourdomain.com` (and the vercel.app URL) to **Authorized JavaScript origins** → Save.
4. **Backend CORS:** confirm Railway `FRONTEND_ORIGIN=https://yourdomain.com` matches exactly (scheme + host, no trailing slash), redeploy if you changed it.

---

## Part 7 — Production smoke test (the moment of truth)

1. Open `https://yourdomain.com` in a **private/incognito window** (clean state).
2. Sign in with a real Google account.
3. Submit an idea: *"Subscription service for personalized dog nutrition in the UK"*.
4. Answer the clarification questions; click approve on the consent card.
5. Watch the progress timeline: research → trends → sections streaming → assembled → export.
6. Read the report. Click **Download PDF**. Open the PDF.
7. Check the Railway worker logs for errors, and Sentry for events.
8. Refresh the page mid-flow on a second run — the session must resume.

If all 8 pass: **you are live.** If something fails, the debugging map is:

| Symptom | Where to look |
|---|---|
| Sign-in popup fails | Google OAuth origins (Part 6 §3), `NEXT_PUBLIC_GOOGLE_CLIENT_ID` |
| API calls fail with CORS errors | `FRONTEND_ORIGIN` on Railway |
| Session starts but nothing happens | Worker service logs (is Celery running? is `REDIS_BROKER_URL` right?) |
| Progress stalls at research | `SERP_API_KEY` invalid or quota exhausted (SerpAPI dashboard) |
| Sections fail | Groq rate limits (worker logs show 429) — wait or upgrade tier |
| PDF download 404s | `EXPORT_STORAGE`/R2 vars on **both** API and worker services |
| SSE never connects | Check the browser network tab for `/stream/events/...`; token query param present? |

---

## Part 8 — Post-deploy routine

- **Deploys are automatic:** push to `main` on GitHub → Railway and Vercel both redeploy. CI (GitHub Actions) must be green before you merge.
- **Weekly:** check Sentry, check SerpAPI/Groq usage dashboards, check Railway spend.
- **Backups:** Neon keeps point-in-time restore on paid tiers; on free tier, run a weekly `pg_dump` (put a recurring calendar reminder): `pg_dump "$DATABASE_URL" > backup-$(date +%F).sql` and keep the last 4 files anywhere safe.
- **Rollback:** Railway → service → **Deployments** → three-dot menu on a previous good deployment → **Redeploy**. Vercel → Deployments → **Promote to Production** on a previous build.
