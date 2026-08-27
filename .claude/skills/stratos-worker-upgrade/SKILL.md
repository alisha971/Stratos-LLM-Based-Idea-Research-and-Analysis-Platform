---
name: stratos-worker-upgrade
description: Implement worker upgrade plans (W1–W9) for the Stratos pipeline — clarification, outline, research, trend, competitor, section writer, embedding, assembler, export workers. Use when upgrading, creating, or testing any Celery worker or its service in stratos-backend/app/workers/ or app/services/.
---

# Stratos Worker Upgrade

How to implement tasks from `stratos-launch-plan/workers/W*.md`. Each worker plan has: current state → feature tasks in order → standalone mode → **testing checklist that gates production**.

## Workflow per worker task

```
- [ ] 1. Read the full W-doc for this worker (not just the one task)
- [ ] 2. If the task adds an LLM call: take the prompt VERBATIM from stratos-launch-plan/prompts/P*.md — do not author prompts freehand
- [ ] 3. Read the existing worker + service files; mimic their patterns (Celery retry config, publish_event usage, fail-soft try/except shape)
- [ ] 4. Implement; wire new events into the contract doc + frontend union (see stratos-contract-guard)
- [ ] 5. Write/extend the tests the W-doc's checklist names for this task
- [ ] 6. Run the worker's full testing checklist section; paste outputs for the release-blocker items
```

## Non-negotiable patterns (from the codebase + plans)

1. **Idempotency by convergent writes:** a worker's first action is checking/deleting its previous output (outline and section workers already model this — delete-before-insert keyed by report/section). Replays must converge.
2. **Fail-soft per provider:** one dead external source costs coverage, never the run. Catch, log, return empty, continue. Emit `*_failed` events only when the whole stage failed.
3. **All outbound page fetches go through the SSRF-guarded fetcher** (`app/utils/safe_fetch.py` once it exists — security plan §5). No bare `requests.get` to internet-derived URLs.
4. **LLM output discipline:** strip code fences → `json.loads` → validate schema → retry once → fail-soft action named in the prompt file. Never let a parse error escape a worker.
5. **Anti-hallucination walls stay:** competitor verification (fetch-or-drop), citation validation, claim audit. Never bypass them "temporarily".
6. **Budgets:** respect per-report caps (queries, scraped pages, LLM calls). New loops must be bounded with deterministic termination.

## Testing gates

- Release-blocker items in each W-doc checklist (marked as such) must pass before the worker ships — e.g. W5's zero-fake-companies eval, W6's adversarial no-fabricated-figures eval, W3's SSRF block-list.
- Always finish with `python scripts/run_pipeline_smoke.py` — a worker upgrade that breaks the pipeline is not done.
- Eval-style tests assert **properties** (citations valid, no invented numbers, honesty disclaimer present), never exact LLM text.

## Build order when free to choose

W3 research → W6 section writer → W5 competitor → W9 export → W8 assembler → W2/W1 → W4 → W7 (rationale in `workers/README.md`).
