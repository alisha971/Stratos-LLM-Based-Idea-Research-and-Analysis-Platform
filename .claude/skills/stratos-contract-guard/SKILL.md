---
name: stratos-contract-guard
description: Enforce the Stratos frontend/backend integration contract when changing API endpoints, request/response shapes, SSE events, or auth flows. Use when editing stratos-backend/app/api/, orchestratorClient.ts, events.ts, chatFlowStore.ts, or any publish_event call site.
---

# Stratos Contract Guard

`stratos-launch-plan/05-INTEGRATION-CONTRACT.md` is the single source of truth for every REST endpoint, payload shape, SSE event, and auth rule. The original codebase drifted (JSON body vs query params, doubled prefixes, mismatched field names) and several calls 422'd at runtime — this skill prevents regressing to that state.

## Before changing any API surface

1. Open the contract doc; find the section for the endpoint/event you're touching.
2. If your change **matches** the contract → proceed.
3. If your change **requires a contract change** → edit `05-INTEGRATION-CONTRACT.md` FIRST, in the same commit, then update **both** sides (backend route/model AND `stratos-frontend/src/lib/api/orchestratorClient.ts` / `src/lib/sse/events.ts` / `src/lib/state/chatFlowStore.ts`).
4. Never ship a one-sided contract change.

## Invariant checklist (verify after any API-adjacent edit)

```
- [ ] Single /orchestrate prefix (owned by main.py include_router; APIRouter has NO prefix)
- [ ] Request bodies are Pydantic models (JSON), never bare function params (query strings)
- [ ] Response fields match the contract exactly (status, report_id, etc. — check spelling)
- [ ] Every SSE payload includes session_id
- [ ] New event types added to BackendEventType union AND a reducer case in chatFlowStore.ts
- [ ] Auth: routes use the JWT dependency; ownership checks return 404 (never 403) for others' resources
- [ ] Errors follow the contract vocabulary: 401 bad token, 402 quota_exceeded, 404 not found/owned, 422 malformed, 429 rate limit
```

## Quick verification commands

- Route shape: start uvicorn, check `http://localhost:8000/docs` — paths and schemas must mirror the contract.
- Event coverage parity: `rg "publish_event" stratos-backend/app/ -A3` vs the union in `stratos-frontend/src/lib/sse/events.ts` — every emitted type should be handled or deliberately ignored (the contract's event catalog says which).
- Frontend still compiles against the shapes: `npm test && npm run build` in `stratos-frontend/`.
