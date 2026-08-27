# 02 — Ship Timeline: Day by Day

> The ~2-week calendar for `01-MVP-IMPLEMENTATION-PLAN.md`. "Day" = one focused working day (6+ hours, or two evenings if you have a day job — then read "day" as ~2 calendar days). Each day ends with an **exit test**; if it fails, tomorrow starts by fixing it, not by moving on.
>
> Written for someone who has never shipped a product. When a step says "see B1.2", open `../stratos-launch-plan/03-BACKEND-COMPLETION-PLAN.md` and find task B1.2 — the full instructions live there.

## Day 0 (prep evening) — Run it locally

- Docker Desktop installed; `docker compose` deps up; backend + worker + frontend running; one manual report generated end-to-end via curl/UI (deployment guide Part 1).
- **Exit test:** a PDF file exists in `exports/` that you generated tonight.

## Day 1 — Backend contract fixes

- Tasks 1.1–1.4 (prefix, JSON bodies, enum, session_id in events).
- **Exit test:** curl the four orchestrate endpoints with JSON bodies → all 200/expected errors; redis subscribe shows session_id everywhere.

## Day 2 — Report reaches the outside world

- Tasks 1.5–1.8 (report endpoint, file endpoint, outline flush, env/CORS/healthz).
- **Exit test:** after a pipeline run, `curl localhost:8000/reports/<id>` returns full sections and the browser downloads the PDF from `/exports/<id>/file`.

## Day 3 — Frontend speaks the same language

- Tasks 4.1–4.2 (client alignment, event union, reducer parity, chunk append, delete mocks).
- **Exit test:** with the dev token, the whole flow runs in the UI and section text streams in live — and nothing in the report panel is placeholder text.

## Day 4 — The full loop in the UI

- Tasks 4.3–4.4 (real report fetch, PDF button, markdown rendering, SSE reconnect).
- **Exit test:** idea → clarify → consent → watch → read → download, all in the browser, zero console errors. Restart the backend mid-run; UI reconnects.

## Day 5 — Auth, backend half

- Tasks 2.1–2.2 (user upsert, JWT dependency, ownership) + security §1 tests.
- **Exit test:** requests without a token → 401; seeded user A cannot read user B's report (404); auth tests green.

## Day 6 — Auth, frontend half

- Tasks 4.5–4.6 (Google Sign-In, middleware, logout, session resume). You'll need the Google OAuth client from doc 06 §2.9 — set it up first thing today.
- **Exit test:** sign in with your real Google account; refresh mid-pipeline resumes; logout locks you out.

## Day 7 — Wallet seatbelts + SSE scoping

- Tasks 2.4–2.5 (server-side SSE filter, rate limits, daily cap) and security item §3 length caps.
- **Exit test:** 6th session in an hour → 429; two accounts in two browsers see only their own events; 10 KB idea → 422.

## Day 8 — SSRF guard + containerization

- Security §5 safe-fetch (morning — it's ~80 lines + tests), then tasks 3.1–3.4 (single-container Dockerfile + start.sh, compose, CI, smoke script).
- **Exit test:** all 8 SSRF tests green; `docker run` locally serves healthz AND processes a full pipeline (both processes alive); smoke script PASS against the container.

## Day 9 — Deploy

- **Hosting decision: Oracle Cloud Always Free, not Railway** — follow [05-ORACLE-DEPLOY.md](05-ORACLE-DEPLOY.md) (one Always Free ARM VM, no trial/expiry, running API + worker + Redis via docker-compose, PDFs on the VM disk, skip R2 entirely, skip anything billing-related). Doc 07 still applies for GitHub/Neon/Astra (Parts 2–3), Vercel (Part 5), and domain + OAuth origins (Part 6); its Railway Part 4 is replaced by doc 05 here.
- **Exit test:** `https://api.yourdomain.com/healthz` → ok; frontend loads on your domain; Google login works in production.

## Day 10 — Production shakedown

- Run the production smoke test (doc 07 Part 7, minus billing rows). Fix what breaks — this day exists BECAUSE something will break (usually: env var typos, OAuth origins, CORS exact-match).
- Generate the 2 sample reports (§6.1); build the minimal landing page (task 4.7) and failure banner (4.8) if not done in gaps earlier.
- **Exit test:** the "done" checklist at the bottom of doc 01 here — every box.

## Day 11 — Private beta

- Send the product to 10–15 people you know (the India playbook Week-0 list if you did it). Personally message each; watch them use it if possible (screen share = gold).
- Fix the top 3 confusions the same day. Log everything in the beta tracker.
- **Exit test:** ≥ 5 strangers-to-the-codebase completed a report without you touching anything.

## Day 12 — Soft public

- Post in 2–3 friendly communities (build-in-public X thread, one subreddit per its rules, one Discord). Frame honestly: "free beta, 10-minute cited market reports, roast it."
- Keep the daily cap at 100; watch Groq/SerpAPI dashboards twice today.
- **Exit test:** ≥ 20 sessions from people you've never met; pipeline completion rate ≥ 80% (check your admin query/logs).

## Day 13–14 — Stabilize + decide

- Fix the crash/confusion list from days 11–12. Read 5 generated reports end-to-end and note quality embarrassments (these become your premium-plan Stage 5 priorities).
- **The decision point** (from doc 01's ending): completion ≥ 30% and ≥ 3 unprompted "can I pay?" signals → proceed to `../stratos-launch-plan/12-DEVELOPER-TIMELINE.md` Stage 5 (worker quality) then Stage 6 (billing). Weak signal → 10 user interviews before writing another line of code.

## Daily habits during all 14 days

1. Morning: read yesterday's logs/Sentry for 5 minutes.
2. One end-of-day git commit minimum; push always (your laptop is not a backup).
3. 30 minutes of build-in-public posting or DM outreach (doc 09 §2.2) — distribution debt compounds exactly like tech debt.
4. Never merge with the smoke script red.

## If you slip (realistic slippage plan)

- Behind by ≤ 2 days: cut task 4.7 landing polish to a bare hero + button, cut 4.4 reconnect (manual refresh is survivable in beta).
- Behind by > 3 days: cut Day 12 soft-public — launch to the private list only, extend a week. **Never cut:** Days 5–8 (auth, SSRF, container) — those are the difference between "beta" and "incident".
