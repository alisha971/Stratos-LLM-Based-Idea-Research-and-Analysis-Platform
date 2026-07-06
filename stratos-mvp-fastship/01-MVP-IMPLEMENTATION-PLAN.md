# 01 — MVP Implementation Plan (Minimum Task List)

> Every task needed to ship, and nothing else. Task IDs like "B1.2" refer to the full specs in `../stratos-launch-plan/03-BACKEND-COMPLETION-PLAN.md` and `04-FRONTEND-COMPLETION-PLAN.md` — read the referenced spec, implement exactly that, skip everything not listed here. Shortcuts unique to fast-ship are marked **[SHORTCUT]** with the premium task that later replaces them.

---

## §1 Backend correctness (must-do, ~2 days)

| # | Task | Spec | Verify |
|---|---|---|---|
| 1.1 | Remove double `/orchestrate/orchestrate` prefix | B1.1 | `/docs` shows single prefix |
| 1.2 | JSON request bodies via Pydantic models | B1.2 | curl with JSON body → 200 |
| 1.3 | Add `EXPORTED` to enum, replace string literals | B1.3 | grep clean |
| 1.4 | `session_id` in every SSE payload | B1.4 | redis-cli subscribe check |
| 1.5 | `GET /reports/{report_id}` | B2.1 | returns sections+chunks+citations |
| 1.6 | `GET /exports/{report_id}/file` — **[SHORTCUT]** local `FileResponse` only, no R2 (premium B6 replaces later; works because of §3.1's single-server deploy) | B2.2 | browser downloads PDF |
| 1.7 | Flush before `outline_ready` payload | B2.3 | non-null section_ids |
| 1.8 | Redis URLs + `FRONTEND_ORIGIN` from env; `.env.example`; CORS middleware; `GET /healthz` | B3.1, B3.2, B3.4 | boots with env config; browser calls pass CORS |

**Skipped from premium:** B2.4 trend gate (races are tolerable — trends just occasionally miss a report), B3.3 requirements pruning, B5 quotas (no billing), B7.3 Alembic (**[SHORTCUT]** keep `create_tables.py`; premium B7.3 later), B8.2 API tests, B9 observability (add free-tier Sentry ONLY if it takes < 30 min — it usually does and is worth it).

## §2 Minimal auth (must-do, ~1.5 days)

You cannot skip auth on a public product whose every use costs you money.

| # | Task | Spec | Verify |
|---|---|---|---|
| 2.1 | Upsert `User` on Google login; `user_id` in JWT | B4.1 | users row appears |
| 2.2 | JWT dependency on orchestrate/reports/exports routes + ownership filters | B4.2 | 401 without token; cross-user 404 |
| 2.3 | **[SHORTCUT]** Keep global SSE stream `/stream/events` but filter **client-side** by `session_id` (premium B4.3 makes it server-side later). Acceptable leak for a small free beta: event *metadata* crosses users, report content doesn't (chunks contain text — mitigate by shipping 2.4). | — | two tabs, two sessions: each UI shows only its own |
| 2.4 | Server-side session filter on SSE — do it if 2.3's leak bothers you; it's ~20 lines (`sse.py` route param + payload check) | B4.3 (partial: skip the per-session auth ticket, just verify JWT + ownership) | second user's events absent from stream |
| 2.5 | Rate limit: `slowapi`, start-session 5/hour/user + a global daily cap of 100 sessions (one Redis counter, 503 past it) | B5.1 + doc 08 §4.3 | 6th call → 429 |

Do 2.4. The shortcut in 2.3 exists only if you're desperately behind schedule.

## §3 Deploy topology (the big fast-ship trick, ~1 day)

| # | Task | Verify |
|---|---|---|
| 3.1 | **[SHORTCUT] Single-container deploy.** One Dockerfile (premium B7.2) plus a `start.sh` that launches BOTH processes: `uvicorn app.main:app --host 0.0.0.0 --port 8000 & celery -A app.workers.celery_app worker --loglevel=info --concurrency=2 & wait -n`. One Railway service instead of two. This is why local-disk PDFs (1.6) work — API and worker share a filesystem. Premium B7.2/B6 splits them later. Add a mounted volume for `exports/` on Railway so PDFs survive restarts. | container runs locally: `docker run` → healthz + a celery banner in logs |
| 3.2 | docker-compose for local postgres+redis | B7.1 | compose up + create_tables works |
| 3.3 | CI: single GitHub Actions job — backend tests + frontend `npm test && npm run build` | B7.4 (merged into one job) | green on push |
| 3.4 | Smoke script | B8.1 | prints PASS |

## §4 Frontend (must-do, ~3 days)

| # | Task | Spec | Verify |
|---|---|---|---|
| 4.1 | Align API client to contract; `.env.example` | F1.1, F1.2 | flow works with dev token |
| 4.2 | SSE event union + reducer parity; chunk **append**; remove all mocks | F2.1, F2.2 | sections stream live |
| 4.3 | Fetch real report on `export_done`; wire PDF button; `react-markdown` rendering | F2.3 | report renders; PDF downloads |
| 4.4 | SSE reconnect with backoff | F2.4 | survives backend restart |
| 4.5 | Google Sign-In + token storage + middleware protection + logout | F3.1, F3.2 | real login gate works |
| 4.6 | Session persistence/resume | F3.3 | refresh resumes |
| 4.7 | **[SHORTCUT] Minimal landing page:** hero + 1 screenshot + 1 sample-report PDF link + a "Join the beta" Google-sign-in button + a one-line "free during beta" note. Skip pricing table, FAQ, demo video (premium F4.2 later). Move app to `/app`. | F4.1 + F4.2 (cut) | `/` loads, converts to `/app` |
| 4.8 | Failed-stage banner + loading spinners (cut version of F4.5: just the red banner + disabled buttons) | F4.5 (cut) | kill a worker → banner shows |

**Skipped from premium:** F4.3 reports history (users have the PDF; add in week 3 if beta sticks), F4.4 billing page (no billing), F5 extra tests beyond keeping the existing 7 green.

## §5 Security — the 5 non-skippable items (~1 day)

From `../stratos-launch-plan/11-SECURITY-PLAN.md`; these are the ones whose absence can end the project in week one:

1. **§1 items 1–4** — JWT enforcement, ownership 404s, strong `JWT_SECRET` + production boot-guard, dev-bypass containment. (Mostly done via §2 above — run the §1 tests.)
2. **§5 SSRF-guarded fetcher** — the scraper fetches arbitrary URLs *today*. All 8 block-tests must pass.
3. **§2 items 1–2** — `.env` gitignored (verify!), secrets only in platform env.
4. **§3 item 1** — length caps on `idea_description` and chat messages (2,000 chars).
5. **§4 via 2.5** — rate limit + global daily cap (your wallet's seatbelt).

Explicitly deferred with eyes open: security headers/CSP, webhook security (no webhooks), deletion endpoint (manual on request during beta — say so in a one-paragraph privacy note in the footer), log scrubbing, pip-audit in CI.

## §6 Launch collateral (~half a day, non-code)

1. Generate 2 good sample reports; link one on the landing page.
2. A feedback channel: a `mailto:` link or a Tally form in the app header ("Beta — tell us what broke").
3. A private "beta tracker" spreadsheet: date, user email, idea, completed?, feedback.

---

## What "done" means for fast-ship

- [ ] Production smoke test (deployment guide Part 7, minus billing steps) passes on your real domain
- [ ] Smoke script PASS against production
- [ ] The 5 security items verified (paste test outputs somewhere you keep)
- [ ] Two different Google accounts fully isolated
- [ ] You personally read one full generated report and didn't wince more than twice

Then: launch per `02-SHIP-TIMELINE.md` days 11–14, and route all "what next" decisions through the beta tracker — if ≥ 30% of beta users complete a report and ≥ 3 ask "can I pay for more?", start the premium plan's Stage 5 (worker upgrades) and Stage 6 (billing). If they don't — you just saved yourself six weeks, and the DM interviews (India playbook Week 0 style) tell you what to change.
