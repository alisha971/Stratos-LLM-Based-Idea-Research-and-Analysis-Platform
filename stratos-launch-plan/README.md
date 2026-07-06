# Stratos Launch Plan — Master Index

**Stratos** is an AI market-research analyst. A user types a startup/market idea, the system asks clarifying questions, researches the web (search results, news, trends, papers), and produces a cited, multi-section market research report as a downloadable PDF — in minutes instead of the days/weeks an analyst or a $2,000 report would take.

This folder is the **complete playbook** to take Stratos from its current state (working-but-rough MVP pipeline) to a **production SaaS with paying users**. It is written so that a junior developer, a low-effort coding model, or even a motivated non-technical person can follow it step by step.

---

## How to use this folder

Read the docs **in order** the first time. After that, jump to whichever doc matches your role.

| # | Doc | What it contains | Who reads it |
|---|-----|------------------|--------------|
| 01 | [Current State Audit](01-CURRENT-STATE-AUDIT.md) | Exactly what is built, partially built, stubbed, and missing — with file paths | Every developer, first day |
| 02 | [Target Architecture](02-TARGET-ARCHITECTURE.md) | The full production system design: services, data stores, event flow, hosting topology | Developers + technical cofounder |
| 03 | [Backend Completion Plan](03-BACKEND-COMPLETION-PLAN.md) | Ordered, numbered micro-tasks to finish the FastAPI/Celery backend | Backend developer |
| 04 | [Frontend Completion Plan](04-FRONTEND-COMPLETION-PLAN.md) | Ordered, numbered micro-tasks to finish the Next.js frontend | Frontend developer |
| 05 | [Integration Contract](05-INTEGRATION-CONTRACT.md) | The single source of truth for REST endpoints, SSE events, auth flow, and payload shapes | Both developers — keep open at all times |
| 06 | [External Dependencies & Costs](06-EXTERNAL-DEPENDENCIES-AND-COSTS.md) | Every third-party service (LLM, search, DBs, hosting, payments), how to sign up, what it costs | Whoever holds the credit card |
| 07 | [Deployment Guide](07-DEPLOYMENT-GUIDE.md) | Click-by-click instructions to deploy everything to the public internet | Anyone — written for a beginner |
| 08 | [Production Hardening & Billing](08-PRODUCTION-HARDENING-AND-BILLING.md) | Auth enforcement, rate limits, quotas, Stripe/Razorpay billing, monitoring, backups | Backend developer, before charging money |
| 09 | [GTM & Marketing Playbook](09-GTM-MARKETING-PLAYBOOK.md) | Positioning, pricing, launch sequence, channels, sales motion — the non-tech cofounder's manual | Business cofounder |
| 10 | [India Indie-Hacker Playbook](10-INDIA-INDIEHACKER-PLAYBOOK.md) | Solo, low-budget path: validate → build → launch → first ₹ revenue, India-specific tools | Solo indie hacker |
| 11 | [Security Plan](11-SECURITY-PLAN.md) | Ordered security implementation: auth, secrets, SSRF, prompt injection, rate limits, privacy — with per-item tests | Any developer/AI agent, alongside phases B4+ |
| 12 | [Developer Timeline](12-DEVELOPER-TIMELINE.md) | The week-by-week map for using this whole folder: which doc, which stage, which exit test | Whoever is implementing — read right after 01 |
| 13 | [Technical Deep-Dive](13-TECHNICAL-DEEP-DIVE.md) | How the system actually works through SDE, agentic-AI, and RAG lenses: event architecture, ranking math, scraper funnel, the full citation lifecycle — with code citations | Anyone who must understand or defend the internals |
| — | [workers/](workers/README.md) | Per-worker upgrade plans (W1–W9) to make each pipeline stage market-competitive and standalone-product-grade, each with its own testing checklist | Developers, after the base plan (Stage 5 of the timeline) |

## Sibling folders

- **`../stratos-mvp-fastship/`** — the ~2-week minimum-steps path to a live free beta. A strict subset of this plan for validating demand fast; its README explains exactly how it differs from this full build.
- **`../stratos-pitch/`** — non-code assets: honest market critique (wrapper vs agentic classification), investor deck script, YC-company internship pitch, and a 6-week X content calendar.

---

## The 30-second status summary (as of July 2026)

**Working today (locally):** A user can start a session, answer clarification questions, approve a summary, and the backend runs research (SerpAPI), trend scanning (HN/GDELT/Google News/arXiv), writes report sections with an LLM (Groq), assembles them, and renders a PDF with ReportLab — all coordinated by Celery workers over Redis, persisting to Postgres and Astra DB.

**Broken / missing for production:**
1. The PDF can never reach the user — no download endpoint, frontend button is a stub.
2. Auth is fake — frontend uses a `demo-token`, backend never checks JWTs on pipeline routes.
3. Frontend and backend API schemas **disagree** (field names, response shapes) — several calls would 422 at runtime.
4. Competitor worker doesn't exist; embedding worker is a no-op; "Competitor Landscape" section is always thin.
5. Zero infrastructure: no Docker, no CI, no migrations, no cloud hosting, no object storage (PDFs land on local disk).
6. Zero business layer: no billing, no quotas, no landing page, no analytics.

**Estimated effort to production:** roughly 4–6 weeks for one full-stack developer following docs 03–08, or 2–3 weeks for two developers working docs 03 and 04 in parallel.

---

## Ground rules for anyone implementing

1. **Doc 05 (Integration Contract) wins all arguments.** If code disagrees with it, fix the code. If the contract must change, change the doc first, in the same PR.
2. **Work top-to-bottom inside each plan.** Tasks are ordered by dependency. Do not skip ahead.
3. **Every task ends with its own verification step.** Do not mark a task done until its "How to verify" passes.
4. **Never commit secrets.** All keys live in `.env` files (gitignored) locally and in the hosting provider's secret manager in production.
5. **Small PRs.** One numbered task = one commit/PR wherever possible.
