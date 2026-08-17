# 15 — Agent Skills: What They Are and How to Use Them

> The repo now ships **seven Cursor Agent Skills** in `.cursor/skills/` — small instruction files that load into an AI coding agent's context when relevant, so the agent follows this project's rules without you re-explaining them every session. This doc explains each skill, when it activates, and how to drive them — written for someone who has never used agent skills before.

## What a skill is (30 seconds)

A skill is a folder in `.cursor/skills/` containing a `SKILL.md` file: a name, a description telling the agent *when* to apply it, and compressed instructions. Because they live in the repo (not on one person's machine), **every person and every AI agent working on Stratos gets the same rules automatically**. Think of them as the enforcement layer for the plan docs: the docs say what to build; the skills make an agent behave while building it.

Two ways a skill activates:
1. **Automatic** — the agent reads skill descriptions and applies whichever matches the current task (most Stratos skills work this way).
2. **Explicit** — you name it in your prompt ("use stratos-deploy"). The deploy skill is explicit-only (`disable-model-invocation: true`) because deployment should never happen as a side effect.

## The seven skills

### Essential (core loop — an agent implementing the project will use these constantly)

| Skill | What it enforces | Auto-triggers when |
|---|---|---|
| **stratos-task-executor** | The 8-step protocol for completing any numbered plan task: read spec → read contract → read code → implement exactly the scope → run the task's Verify step → tests → smoke script → one commit per task. Plus the hard rules (never weaken a check; contract wins; dependency order) | Implementing anything referenced by a task ID (B1.2, F3.1, W5-K2, §5, fast-ship 4.3) |
| **stratos-contract-guard** | Both-sides-or-neither API changes: the invariant checklist (single prefix, Pydantic bodies, session_id in every event, 404-not-403, event union parity) and the rule that `05-INTEGRATION-CONTRACT.md` is edited first, in the same commit | Editing `app/api/`, `orchestratorClient.ts`, `events.ts`, `chatFlowStore.ts`, or any `publish_event` call |
| **stratos-worker-upgrade** | The worker patterns: idempotency by convergent writes, fail-soft per provider, SSRF-guarded fetching, bounded LLM loops, budgets, and the W-doc testing gates (release-blockers must show pasted output) | Touching `app/workers/` or `app/services/`, or implementing any W1–W9 task |
| **stratos-security-gate** | The non-negotiables: pinned JWT algorithms, ownership 404s, the SSRF block-list, prompt-injection boundaries, secret grep, cost caps, webhook signatures — and the golden rule (never weaken a check to pass a test) | Editing auth/fetching/webhook/prompt-boundary code, or any security review request |

### Supplementary (situational)

| Skill | What it provides | Triggers |
|---|---|---|
| **stratos-llm-prompts** | Prompt discipline: use the P1–P7 library verbatim, `{{PLACEHOLDER}}` + `.replace()` (never f-strings), `<data>` tag injection boundaries, the mandatory parse-retry-failsoft shape, the ≤45-calls-per-report budget | Writing/changing prompts or LLM JSON handling |
| **stratos-pipeline-debug** | The diagnostic map: stuck-state → cause table, task-lost vs event-lost decision procedure, quality-debugging steps (source_mode, evidence counts, ranking reasons), the smoke script as golden repro | A run is stuck, failed, or producing bad reports |
| **stratos-deploy** (explicit-only) | Production topology, env var sets per service, pre-deploy gates, the production-only failure map, rollback steps | Only when you say "deploy" / "use stratos-deploy" |

## How to drive them (recipes)

**Giving an agent a plan task** — you don't need to mention skills at all; the task ID triggers the executor:
> "Implement task B2.1 from the backend completion plan."
The executor skill makes it read the spec + contract first and finish with verification output. If it touches the API surface, contract-guard stacks on top automatically. Skills compose.

**Delegating a whole phase to a smaller model:**
> "Work through Phase B4 of stratos-launch-plan/03-BACKEND-COMPLETION-PLAN.md, one task per commit, in order."
The executor's checklist keeps a weaker model on rails: it can't skip verification steps without visibly violating the protocol, and the security gate stops the classic weaken-the-test failure mode.

**Reviewing an agent's (or your own) changes:**
> "Review this diff against stratos-contract-guard and stratos-security-gate."
Both skills contain explicit checklists — the review becomes box-ticking with evidence, not vibes.

**Debugging without dumping context:**
> "A session is stuck in RESEARCH_RUNNING — debug it."
The debug skill loads the stuck-state table and the event-vs-task procedure; the agent starts from the right queries instead of rediscovering the architecture.

**Deploying (explicit by design):**
> "Use stratos-deploy to ship the current main to production."

## How skills relate to the plan docs

Skills are **compressed pointers, not replacements**. Each one links to its authoritative doc (03/04 plans, 05 contract, 11 security, 07 deployment, prompts/ library) and holds only the rules that must survive even when the agent doesn't open the full doc. Precedence when things conflict: **contract doc > plan doc > skill > agent's judgment** — and a conflict means a doc needs updating, in the same commit.

## Maintaining the skills

- A recurring correction you keep typing to agents = a missing rule; add one line to the relevant skill rather than growing it into an essay. Skills compete for context — keep each under ~60 lines of substance.
- When a plan doc changes materially (e.g. new invariant in the contract), update the corresponding skill in the same PR.
- Adding a new skill: follow the create-skill conventions — lowercase-hyphen name, third-person description containing *what* + *when* trigger terms, under 500 lines, one level of file references. Put it in `.cursor/skills/<name>/SKILL.md` so it ships with the repo.
- Verify a skill is discoverable: start a fresh agent session and give it a task matching the skill's trigger description — it should follow the skill's protocol without being told the skill's name.
