---
name: stratos-task-executor
description: Execute numbered implementation tasks from the Stratos plan docs (B1.2, F3.1, W5-K2, security §5, fast-ship 4.3, etc.). Use whenever implementing, continuing, or being asked to "do the next task" from stratos-launch-plan/, stratos-mvp-fastship/, or the workers/ folder.
---

# Stratos Task Executor

The protocol for completing one numbered task from the Stratos implementation plans. Task IDs map to docs: `B*` → `stratos-launch-plan/03-BACKEND-COMPLETION-PLAN.md`, `F*` → `04-FRONTEND-COMPLETION-PLAN.md`, `W#-*` → `stratos-launch-plan/workers/W#-*.md`, `§*` → `11-SECURITY-PLAN.md`, plain numbers like `4.3` → `stratos-mvp-fastship/01-MVP-IMPLEMENTATION-PLAN.md`.

## Protocol

Copy this checklist and track it:

```
- [ ] 1. Read the task's full spec in its plan doc (not just the summary table)
- [ ] 2. Read 05-INTEGRATION-CONTRACT.md sections the task touches
- [ ] 3. Read the existing code files the task names BEFORE writing anything
- [ ] 4. Implement exactly the task scope — no extras, no drive-by refactors
- [ ] 5. Run the task's own "Verify" step; paste its output
- [ ] 6. Run the relevant test suite + linter on touched files
- [ ] 7. Run scripts/run_pipeline_smoke.py if the task touches pipeline code
- [ ] 8. One commit for the task, message referencing the task ID
```

## Hard rules

1. **Never weaken a check, test, or validation to make something pass.** If a security or validation test fails, the implementation is wrong, not the test. This rule has no exceptions.
2. **`05-INTEGRATION-CONTRACT.md` wins all arguments.** If code and contract disagree, fix the code. If the contract must change, edit the contract file in the same commit.
3. **Work in dependency order.** If a task's spec references an earlier incomplete task (e.g. B4.2 needs B4.1), do the prerequisite first or stop and say so.
4. **Every SSE payload must include `session_id`.** Any new `publish_event` call site follows this.
5. **Fail-soft discipline:** new external calls (HTTP, LLM, DB beyond Postgres/Redis) need a timeout, error handling, and a degradation path that keeps the pipeline alive. Record degradation in data or logs, never silently.
6. Don't mark a task done without step 5's verification output. "It should work" is not done.

## Windows dev notes

- Celery needs `--pool=solo` on Windows.
- Activate venv: `.\venv\Scripts\Activate.ps1` in `stratos-backend/`.
- Local deps: `docker compose up -d` in `stratos-backend/` (postgres + redis).

## When stuck

Blocked > 30 min on one task: leave `# TODO(blocked): <reason>` at the site, report the blocker precisely (what was tried, what failed), and ask before improvising around it.
