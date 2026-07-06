# Stratos MVP Fast-Ship — Read This First

## What this folder is

The **shortest possible path** from the code that exists today to a **live, public, usable product on the internet**. Not the best product — the fastest shippable one. Target: **10–14 working days** for one developer (or one person + an AI coding agent).

## How this differs from `../stratos-launch-plan/`

There are two plans in this repo. Pick one deliberately:

| | **This folder (fast-ship)** | **`stratos-launch-plan/` (premium)** |
|---|---|---|
| Goal | Get real users on a live URL ASAP, learn if anyone cares | A market-competitive, secured, billable SaaS |
| Timeline | ~2 weeks | ~8–10 weeks |
| Report quality | Whatever today's pipeline produces (decent, imperfect) | Upgraded workers: audited citations, real competitor analysis, charts, executive summary |
| Billing | None — free beta, waitlist for demand proof | Stripe/Razorpay, plans, quotas |
| Auth | Real Google login, but minimal (it's cheap and unavoidable) | Full auth + ownership + session-scoped SSE |
| Infra | One server running everything; PDFs on its disk | Split services, R2 object storage, CI, Alembic, Sentry |
| Security | The 5 items you may not skip (listed in doc 01 here) | The full `11-SECURITY-PLAN.md` |
| Worker upgrades | Zero | All 9 worker plans |

**The relationship between the two:** fast-ship is a strict subset. Every task here is either a task from the premium plan (referenced by its number, e.g. "B1.2") or a documented shortcut with the exact premium task that later replaces it. Nothing you build here is thrown away — after shipping, you continue into the premium plan's Stage 5+ if the beta shows demand.

**When to choose fast-ship:** you're solo, budget-constrained, unsure of demand, and the most valuable thing you can buy is *information from real users*. (This is the doc-10-India-playbook philosophy: validate before polishing.)

**When to choose premium directly:** you already have validated demand (e.g. Week-0 DMs from the India playbook said yes loudly), or a cofounder/funding gives you runway to build the moat first.

## The docs in this folder

| Doc | Contents |
|---|---|
| [01-MVP-IMPLEMENTATION-PLAN.md](01-MVP-IMPLEMENTATION-PLAN.md) | The minimal task list — every code change needed, nothing more |
| [02-SHIP-TIMELINE.md](02-SHIP-TIMELINE.md) | Day-by-day schedule for the ~2 weeks, with daily exit tests |

## Ground rules (same as the premium plan)

1. `../stratos-launch-plan/05-INTEGRATION-CONTRACT.md` is still law — fast-ship implements a subset of it, never a variant of it.
2. Every task ends with its verification step. No exceptions because "we're moving fast" — unverified speed is just deferred slowness.
3. The 5 non-skippable security items (doc 01 §5 here) are non-skippable. Everything else security-wise is honestly deferred.
