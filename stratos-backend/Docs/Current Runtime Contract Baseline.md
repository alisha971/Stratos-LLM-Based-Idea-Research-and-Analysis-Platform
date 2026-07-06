# Current Runtime Contract Baseline

Status: Implemented baseline (as-built snapshot)

## Purpose
This document is the source of truth for what is currently implemented and callable in the backend runtime.

## Runtime Surface (Implemented)

### API routes
- `GET /` health route.
- `POST /auth/google`
- `GET /stream/events`
- Orchestrator routes are currently exposed under double prefix because both app and router define `/orchestrate`:
  - `POST /orchestrate/orchestrate/start-session`
  - `POST /orchestrate/orchestrate/clarification/chat`
  - `POST /orchestrate/orchestrate/clarification/accept-consent`
  - `GET /orchestrate/orchestrate/status/{session_id}`

### Event channel
- Redis pub/sub channel: `stratos_events`
- SSE bridge streams event payload JSON from `stratos_events`.

### Implemented workers/tasks
- `run_clarification(session_id)`
- `run_outline(report_id)`
- `run_research(report_id)`

### Implemented orchestrator states
- `CREATED`
- `CLARIFYING`
- `AWAITING_CONSENT`
- `READY_FOR_RESEARCH`
- `OUTLINE_GENERATED`
- `RESEARCH_RUNNING`

## Current End-to-End Implemented Flow
1. Client creates session via start-session endpoint.
2. Orchestrator seeds initial chat and triggers clarification worker.
3. Clarification emits `clarification_update` and eventually `clarification_ready`.
4. Event listener transitions session to `AWAITING_CONSENT` and emits `clarification_consent_requested`.
5. Client accepts consent and orchestrator emits `clarification_completed`, then triggers outline worker.
6. Outline worker persists sections and emits `outline_ready`.
7. Event listener transitions to `OUTLINE_GENERATED`, emits `outline_accepted`, then moves to `RESEARCH_RUNNING` and emits `research_started`.
8. Research worker emits `searching_sources` then `research_done` or `research_failed`.

## Persistence Reality (Implemented)
- Used in flow: sessions, reports, chat_messages, sections, sources, source_evidence.
- Modeled but not active in full pipeline yet: trends, competitors, report_chunks, citations, exports.

## Known Contract Mismatches (Docs vs Runtime)

| ID | Mismatch | Runtime Today | Target (MVP docs) | Owner | Resolution Target |
|---|---|---|---|---|---|
| M1 | Orchestrator route prefix | `/orchestrate/orchestrate/*` | `/orchestrate/*` | Backend API | Normalize router/app prefix once |
| M2 | Auth on orchestrator endpoints | No JWT dependency enforced | JWT-protected session actions | Backend API | Add auth dependency before public release |
| M3 | Worker inventory in docs | Docs describe full pipeline as active | Only clarification/outline/research active | Docs + Backend | Mark others as planned contracts |
| M4 | Research Astra persistence | `save_to_astra` is stub | Persist vector/raw evidence in Astra | Research worker | Implement in later sprint |
| M5 | Event richness | Limited event set in runtime | Rich progress model in docs | Research worker + SSE | Expand event taxonomy later |
| M6 | Export/deep-dive readiness | Not wired end-to-end | Planned post core MVP | Product + Backend | Add after writer/assembler stages |

## Planned But Not Implemented (for blueprint docs)
- Trend Worker
- Competitor Worker
- Section Writer Worker
- Embedding Worker
- Assembler Worker
- Export Worker

