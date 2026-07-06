# 04 — Frontend Completion Plan

> Ordered micro-tasks for `stratos-frontend/`. Depends on the backend phases noted per task — coordinate with doc 03. Keep doc 05 (Integration Contract) open at all times.
>
> Stack reminder: Next.js 16 App Router, React 19, Tailwind 4, Vitest. Note the repo rule in `stratos-frontend/AGENTS.md`: this Next.js version may differ from what you remember — check `node_modules/next/dist/docs/` before using an API you're unsure about.

---

## Phase F1 — Align the API client with the contract (half a day; needs backend B1)

### F1.1 Rewrite `orchestratorClient.ts` to the doc 05 contract

- Single prefix paths: `/orchestrate/start-session`, `/orchestrate/clarification/chat`, `/orchestrate/clarification/accept-consent`, `/orchestrate/status/{id}`.
- Field names: send `{idea_description}` (not `idea_input`), `{session_id, message}` (not `user_input`).
- Response types updated to doc 05 §3 (status returns `status`, `report_id`, `report_status`, `clarified_summary`).
- Add `fetchReport(reportId)` → `GET /reports/{report_id}` and `getExportFileUrl(reportId)` → the string `${API_BASE_URL}/exports/{reportId}/file`.
- All requests attach `Authorization: Bearer ${token}`; add a `setAuthToken(token)` module function (or pass token per call — pick one and be consistent).
- **Verify:** with backend running, the full clarify → consent flow works from the UI with the dev token (`dev`, see backend B4.2), and no request 4xxs in the network tab.

### F1.2 Create `.env.example` + README update

- **File:** `stratos-frontend/.env.example` — `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` and `NEXT_PUBLIC_GOOGLE_CLIENT_ID=`.
- Replace the boilerplate `README.md` with actual run instructions (backend must be up first, copy `.env.example` → `.env.local`).

---

## Phase F2 — Real event coverage & streaming report (1–2 days; needs backend B1.4, B2)

### F2.1 Complete the SSE event union

- **File:** `src/lib/sse/events.ts` — add missing `BackendEventType` members: `session_created`, `clarification_started`, `clarification_completed`, `outline_accepted`, `section_writing_started`, `section_started`, `sections_done`, `report_assembled`, `assembler_failed`, `trend_failed`, `embedding_skipped`.

### F2.2 Reducer parity + remove mocks

- **File:** `src/lib/state/chatFlowStore.ts`:
  - `section_chunk` **appends** to `partialText` (currently replaces). Keyed by `section_id`.
  - Delete the mock section inserted on `research_done` and the placeholder final-report text on `export_done`.
  - Add progress-timeline entries for the new events (`section_writing_started` → "Writing sections…", `report_assembled` → "Assembling report…", etc.).
  - `outline_ready` stores `reportId` and the section list (ids now non-null after backend B2.3) so the report panel can pre-render section skeletons.
  - `trend_failed` / `assembler_failed` / `section_failed` / `export_failed` → explicit `failed` handling with the event's `error` message stored in state (stop relying on the `includes("failed")` substring hack, but keep it as a fallback).
- **Verify:** `npm test` (update the two store tests that asserted mock behavior); manual run shows sections streaming token-by-token in the right panel.

### F2.3 Fetch the real report on `export_done`

- On `export_done`, call `fetchReport(reportId)` and store the result as `finalReport` (sections → chunks → citations). `ReportSplitPanel` renders it with `react-markdown` (add dependency: `npm i react-markdown`), citations as superscript `[n]` links to source URLs.
- Wire `PdfDownloadButton` to open `getExportFileUrl(reportId)` in a new tab (the backend serves/redirects the PDF). Remove the "not yet enabled" stub in `ChatShell.handleDownloadPdf`.
- Add a distinct `reportReady` UI: composer disabled with a "Report complete" note, download button highlighted.
- **Verify:** end-to-end run finishes with the real report rendered and the PDF downloading.

### F2.4 Robust SSE connection

- **File:** `src/lib/sse/useEventStream.ts` — on error, actually close and reopen the `EventSource` with exponential backoff (1 s → 2 s → 4 s → max 30 s), reset backoff on successful message. Point at the session-scoped URL `GET /stream/events/{session_id}?token=...` once backend B4.3 lands (until then keep the global stream but filter client-side by `payload.session_id`).
- **Verify:** kill and restart the backend while the app is open; the stream reconnects and the status badge recovers.

---

## Phase F3 — Real auth (1 day; needs backend B4)

### F3.1 Google Sign-In on `/login`

- Add Google Identity Services (`@react-oauth/google` or the plain GSI script). On credential response, `POST /auth/google` with the `id_token`; receive the app JWT.
- Store the JWT: simplest robust MVP approach — a Next.js route handler `POST /api/session` sets it in an **httpOnly cookie**, and a matching `GET /api/session` returns it to client code at boot (or keep it in memory + `localStorage` if you accept the XSS tradeoff for MVP; pick one, document it in code).
- **Verify:** sign in with a real Google account; a `users` row exists in Postgres; the JWT is attached to subsequent API calls.

### F3.2 Route protection + logout

- **File:** `src/middleware.ts` (new) — redirect unauthenticated visitors of `/app/*` to `/login`.
- Remove the inline demo-login gate from `ChatShell.tsx` entirely. Logout clears the cookie and redirects to `/`.
- **Verify:** visiting `/app` logged-out redirects to `/login`; after login you land back on `/app`.

### F3.3 Session persistence & resume

- Persist `sessionId` + `reportId` in `localStorage`. On boot with a stored session, call `GET /orchestrate/status/{id}`: if terminal (`EXPORTED`), fetch and show the report; if mid-pipeline, reopen SSE and show the timeline; if `CLARIFYING`/`AWAITING_CONSENT`, restore chat via the status payload.
- Add a "New report" button that clears the stored session.
- **Verify:** refresh mid-run — the UI resumes instead of resetting.

---

## Phase F4 — Product surface (2–3 days)

### F4.1 Restructure routes

- Move the chat workspace from `/` to `/app` (`src/app/app/page.tsx`). `/` becomes the landing page.
- Delete `BackendSequenceMap.tsx` (dev artifact) or move it behind a `?debug=1` flag.

### F4.2 Landing page at `/`

Static, server-rendered, SEO-tagged (`metadata` export). Sections:
1. Hero: headline ("Investor-grade market research in 10 minutes"), subhead, CTA button → `/login`, and a looping 20-second screen recording (record once the pipeline works — see doc 09 §4 for the script).
2. "How it works" — 3 steps with the actual product screenshots.
3. Sample report — link to a real PDF generated by the system (host the file in `public/`).
4. Pricing table (mirrors doc 08 plans) with CTA per tier.
5. FAQ (data sources, citations, refund policy) + footer (privacy, terms — see doc 09 §8 for templates).
- **Verify:** Lighthouse SEO + performance ≥ 90 on the landing page.

### F4.3 Reports history page

- `src/app/app/reports/page.tsx` — list from `GET /reports` (backend adds this trivial listing route in B2 if not already): title (idea), date, status, download link. Clicking a report opens it read-only in the split panel.
- **Verify:** two completed reports both appear and re-download.

### F4.4 Billing page

- `src/app/billing/page.tsx` — current plan, usage meter (`reports_used_this_month / limit` from a `GET /billing/me` endpoint, doc 08), upgrade buttons hitting `POST /billing/checkout` and redirecting to the provider's hosted checkout. Handle the `?success=1` / `?canceled=1` return params with a banner.
- **Verify:** test-mode checkout completes and the plan updates (full loop specified in doc 08).

### F4.5 Error & loading polish

- Failed stage UI: red banner with the stored error message and a "Start over" button.
- Loading states on every REST call (disable + spinner on buttons).
- Quota-exceeded (402) and rate-limit (429) responses get friendly messages with an upgrade link.
- An `error.tsx` boundary under `/app`.
- **Verify:** simulate each failure (kill a worker mid-run; exhaust quota with a free account) and confirm the UI response.

---

## Phase F5 — Tests & CI (1 day)

- Update/extend Vitest suites: store reducer cases for the new events (chunk append, export_done fetch trigger), client contract types, middleware redirect logic.
- Add one Playwright smoke test (optional but recommended): login-bypassed dev mode → start session → reach consent card. Run it in CI against a mocked backend or skip in CI and keep it as a local pre-release check.
- **Verify:** `npm test` and `npm run build` green locally and in the GitHub Actions job from backend task B7.4.

---

## Definition of done (frontend)

- [ ] A brand-new user can: land on `/`, sign in with Google, submit an idea, answer clarifications, approve consent, watch live progress, read the full cited report, and download the PDF — with zero console errors.
- [ ] Refreshing at any point resumes the session.
- [ ] Free-tier quota exhaustion shows the upgrade path.
- [ ] `npm run build` passes; Lighthouse ≥ 90 on `/`.
