# 05 — Integration Contract (Single Source of Truth)

> **This document wins all arguments.** Backend and frontend both implement exactly what is written here. If the contract must change, edit this file in the same PR as the code change.
>
> Base URL: `NEXT_PUBLIC_API_BASE_URL` (dev: `http://localhost:8000`). All request/response bodies are JSON. All timestamps are ISO-8601 UTC.

## 1. Authentication

- Client obtains a Google ID token via Google Identity Services, exchanges it at `POST /auth/google`, and receives an app JWT (HS256, 7-day expiry, claim `sub` = user id).
- Every request below **except** `/auth/google` and `/healthz` requires header `Authorization: Bearer <jwt>`.
- SSE (browsers cannot set headers on `EventSource`): pass the JWT as `?token=<jwt>` query param.
- Dev-mode escape hatch: when the backend runs with `ENV=development` and `DEV_AUTH_BYPASS=true`, the literal token `dev` authenticates as user `dev-user`.
- Error responses everywhere: `401` invalid/missing token, `404` resource not found or not owned by caller, `402 {"detail":"quota_exceeded"}`, `429` rate-limited, `422` malformed body.

### 1.1 `POST /auth/google`

Request: `{ "id_token": "<google id token>" }`
Response 200:

```json
{ "access_token": "<jwt>", "token_type": "bearer", "user": { "id": "…", "email": "…", "name": "…", "plan": "free" } }
```

## 2. Session state machine (shared vocabulary)

`CREATED → CLARIFYING → AWAITING_CONSENT → READY_FOR_RESEARCH → OUTLINE_GENERATED → RESEARCH_RUNNING → WRITING_SECTIONS → READY_FOR_ASSEMBLY → READY_FOR_EXPORT → EXPORTED`

Report `status` mirrors the tail states; terminal success is `EXPORTED`.

## 3. REST endpoints

### 3.1 `POST /orchestrate/start-session`

Request: `{ "idea_description": "AI meal planner for diabetics" }` (user identity from JWT)
Response 200:

```json
{ "session_id": "…", "report_id": "…", "status": "CLARIFYING", "message": "Session created. Clarification started." }
```

Rate limit: 5/hour/user. Quota: counts against `reports_used_this_month`.

### 3.2 `POST /orchestrate/clarification/chat`

Request: `{ "session_id": "…", "message": "B2C, US market, subscription" }`
Response 200: `{ "session_id": "…", "status": "CLARIFYING" }`
Errors: `400` if session not in `CLARIFYING`.

### 3.3 `POST /orchestrate/clarification/accept-consent`

Request: `{ "session_id": "…" }`
Response 200: `{ "session_id": "…", "status": "READY_FOR_RESEARCH", "message": "Clarification accepted. Research can begin." }`
Errors: `400` if session not in `AWAITING_CONSENT`.

### 3.4 `GET /orchestrate/status/{session_id}`

Response 200:

```json
{
  "session_id": "…",
  "status": "WRITING_SECTIONS",
  "idea_description": "…",
  "clarified_summary": "… or null",
  "report_id": "…",
  "report_status": "WRITING_SECTIONS"
}
```

### 3.5 `GET /reports`

Response 200: `{ "reports": [ { "report_id": "…", "session_id": "…", "idea_description": "…", "status": "EXPORTED", "created_at": "…" } ] }` — caller's reports only, newest first.

### 3.6 `GET /reports/{report_id}`

Response 200:

```json
{
  "report_id": "…",
  "status": "EXPORTED",
  "title": "Market Research: <idea>",
  "sections": [
    {
      "section_id": "…",
      "title": "Market Overview",
      "order_index": 0,
      "chunks": [
        {
          "chunk_id": "…",
          "order_index": 0,
          "text": "… markdown text with [CIT-001] markers …",
          "citations": [
            { "marker": "CIT-001", "url": "https://…", "domain": "example.com", "title": "…" }
          ]
        }
      ]
    }
  ]
}
```

### 3.7 `GET /exports/{report_id}/file`

- Dev (`EXPORT_STORAGE=local`): `200` with `Content-Type: application/pdf`, `Content-Disposition: attachment; filename="stratos-report.pdf"`.
- Prod (`EXPORT_STORAGE=r2`): `302` redirect to a presigned R2 URL (1-hour expiry).
- `404` if no export record yet.

### 3.8 Billing (see doc 08 for provider details)

- `GET /billing/me` → `{ "plan": "free", "reports_used_this_month": 1, "limit": 2, "quota_reset_at": "…" }`
- `POST /billing/checkout` with `{ "plan": "starter" | "pro" }` → `{ "checkout_url": "https://…" }`
- `POST /billing/webhook` — provider → backend only; verifies signature; updates `users.plan`.

### 3.9 `GET /healthz`

`{ "ok": true }` — no auth. Used by hosting health checks.

## 4. SSE: `GET /stream/events/{session_id}?token=<jwt>`

- Content type `text/event-stream`. Each message's `data:` is JSON: `{ "type": "<event>", "payload": { … } }`.
- **Every payload includes `session_id`.** The server only forwards events for the session in the path (after verifying ownership).
- The client must tolerate unknown event types (ignore, don't crash).

### 4.1 Event catalog

| Type | Key payload fields (besides `session_id`) | Frontend reaction |
|---|---|---|
| `session_created` | — | none (informational) |
| `clarification_started` | — | timeline entry |
| `clarification_update` | `question` (assistant's next question), `confidence` | append assistant chat message |
| `clarification_ready` | `summary` | internal (precedes consent request) |
| `clarification_consent_requested` | `summary` | show consent card, stage → `awaitingConsent` |
| `clarification_completed` | — | timeline entry |
| `outline_accepted` | — | timeline entry |
| `outline_ready` | `report_id`, `sections: [{section_id, title, order_index}]` (ids non-null) | store reportId, pre-render section skeletons |
| `research_started` | — | stage → `researching` |
| `searching_sources` | `query` or `count` | timeline entry |
| `research_done` | `sources_count` | timeline entry |
| `research_failed` | `error` | stage → `failed` |
| `scanning_trends` | — | timeline entry |
| `trend_ready` | `items_count` | timeline entry |
| `trend_failed` | `error` | timeline warning (pipeline continues) |
| `section_writing_started` | `sections_total` | stage → `streamingSections` |
| `section_started` | `section_id`, `title` | highlight active section |
| `section_chunk` | `section_id`, `text` (delta) | **append** to section's partial text |
| `section_done` | `section_id` | mark section complete |
| `section_failed` | `section_id`, `error` | mark section failed |
| `sections_done` | — | timeline entry |
| `report_assembled` | `report_id` | timeline entry ("Assembling…") |
| `assembler_failed` | `error` | stage → `failed` |
| `export_done` | `report_id`, `file_url` | fetch `GET /reports/{id}`, enable PDF button, stage → `reportReady` |
| `export_failed` | `error` | stage → `failed` |
| `embedding_skipped` | `reason` | ignore |

## 5. CORS

Backend allows origin `FRONTEND_ORIGIN` (env), credentials on, all methods/headers. Dev: `http://localhost:3000`. Prod: the Vercel domain(s).

## 6. Versioning discipline

No `/v1` prefix for MVP (single first-party client). Breaking changes require: update this doc → backend → frontend, all in one coordinated deploy window.
