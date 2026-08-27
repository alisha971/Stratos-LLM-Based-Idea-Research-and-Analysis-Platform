---
name: stratos-pipeline-debug
description: Diagnose stuck, failed, or low-quality Stratos pipeline runs — sessions frozen in a state, missing SSE events, empty sections, broken PDFs, Celery tasks not executing. Use when a report run misbehaves or when asked "why is the pipeline stuck/broken".
---

# Stratos Pipeline Debug

Diagnostic map for the clarify → outline → research∥trend → sections → assemble → export pipeline. Full mechanics: `stratos-launch-plan/13-TECHNICAL-DEEP-DIVE.md`.

## First moves (always, in order)

1. **Where is it stuck?** Check the session/report state:
   `SELECT id, status FROM sessions WHERE id='...';` and `SELECT id, status FROM reports WHERE session_id='...';`
   The state names the failed stage: e.g. stuck `RESEARCH_RUNNING` → research/trend never completed.
2. **Is Celery alive and consuming?** Worker terminal shows the banner + task lines. No tasks arriving → broker URL mismatch (`REDIS_BROKER_URL`) or worker not started (`--pool=solo` needed on Windows).
3. **Are events flowing?** `redis-cli -n 1 subscribe stratos_events` during a run. Events flowing but state not advancing → the API-process listener thread is dead (restart uvicorn; it starts in the FastAPI lifespan).

## Stuck-state → cause table

| Stuck in | Likely cause | Check |
|---|---|---|
| CLARIFYING forever | LLM call failing (Groq key/rate limit) or confidence never reaching 0.95 | worker logs for the clarification task; Groq dashboard |
| AWAITING_CONSENT | Not a bug — waiting for the user's consent POST | frontend consent card shown? |
| READY_FOR_RESEARCH / no outline | outline task failed post-retries | worker logs; LLM JSON parse errors |
| RESEARCH_RUNNING forever | SerpAPI quota/key dead, or `research_done` event lost (listener down) | SerpAPI dashboard; redis-cli subscribe |
| WRITING_SECTIONS forever | one section failing repeatedly (validation loop), or fan-in count never reached | `SELECT title, status FROM sections WHERE report_id='...';` find the stuck one |
| READY_FOR_EXPORT / no PDF | export task failed (ReportLab crash — usually unescaped `<` in text) or exports/ not writable | worker logs for export task |

## Event lost vs task lost

- Task dispatched but never ran → broker plane (Redis DB 0): worker down, wrong URL.
- Task ran (logs show completion) but state didn't advance → event plane (Redis DB 1): listener thread dead, or payload missing `session_id`/`report_id` keys the handler needs. Pub/sub is fire-and-forget — an event published while the listener was down is gone; re-trigger by re-dispatching the completed stage's task (workers are idempotent: delete-before-insert converges).

## Quality debugging (report is bad, not broken)

1. Which evidence mode? Astra items carry `source_mode` — `postgres_fallback` means Astra was down/unset → thinner sections.
2. Evidence thin? `SELECT count(*) FROM sources WHERE report_id='...';` <10 sources → research underperformed (check which SERP engines returned empty in logs).
3. Section validation looping? Worker logs show repair reasons — recurring "unknown citation marker" usually means the bundle was empty/tiny for that section.
4. Ranking junk? Evidence items store their scoring `reason` string — inspect the bundle in Astra/logs. Known issue: ranker vocabularies are overfit (see `14-DESIGN-DECISIONS.md` D13).

## Golden reproduction

`python scripts/run_pipeline_smoke.py` (dev token, fixed idea) is the canonical repro. If smoke passes but a user run fails, diff the variables: idea content (length caps? odd characters?), auth path, concurrent runs.
