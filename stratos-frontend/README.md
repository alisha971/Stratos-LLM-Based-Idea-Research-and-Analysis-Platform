# Stratos Frontend

Next.js 16 (App Router) + React 19 + Tailwind 4 client for the Stratos research
pipeline. Talks to `stratos-backend` over REST + SSE.

## Prerequisites

- Node 20+
- **The backend must be running first** (`stratos-backend`) — this app is a thin
  client over its API.

## Setup

```bash
cp .env.example .env.local     # then edit it
npm install
npm run dev                    # http://localhost:3000
```

### Environment

See `.env.example` and `../stratos-mvp-fastship/03-ENV-AND-KEYS.md` for details.

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend base URL (default `http://localhost:8000`). |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Google OAuth client id. Leave empty locally and use the **"Continue in dev mode"** button on `/login` (requires backend `DEV_AUTH_BYPASS=true`). |

## Routes

- `/` — public landing page.
- `/login` — Google Sign-In (+ dev-mode button locally).
- `/app` — the research workspace (gated by `src/proxy.ts`; redirects to `/login` without a session cookie).

## Scripts

```bash
npm test          # vitest
npm run lint      # eslint (zero warnings enforced)
npm run build     # production build (needs internet for Google Fonts)
```
