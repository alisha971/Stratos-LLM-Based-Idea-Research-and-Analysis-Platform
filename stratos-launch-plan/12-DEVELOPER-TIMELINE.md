# 12 — Developer Timeline: How to Actually Use This Folder

> You have 12 docs and 9 worker plans. This doc is the map that tells you **what to read when, what to build in which week, and how to know you're on track**. It assumes one full-time developer (or one person directing AI coding agents). Two developers can roughly halve the calendar by splitting backend/frontend where marked.
>
> If you want the fastest possible launch with fewer features instead, use the **`../stratos-mvp-fastship/`** folder — that's the "ship in ~2 weeks" path. THIS timeline is the full premium build (~8–10 weeks) that ends with a market-competitive, secured, billable product.

## The one-page rule

At any moment you should be able to answer: *"Which numbered task am I on, and does its verification step pass?"* If you can't, stop and re-find your place. Never work on two phases at once.

---

## Stage 0 — Orientation (Day 1)

1. Read `README.md`, `01-CURRENT-STATE-AUDIT.md`, skim `02-TARGET-ARCHITECTURE.md`.
2. Get the system running locally: doc `07-DEPLOYMENT-GUIDE.md` **Part 1 only** (local run). This is non-negotiable — you cannot fix what you cannot run.
3. Bookmark `05-INTEGRATION-CONTRACT.md`. It stays open in a tab for the next two months.

**Exit test:** the manual local run (Part 1 step 8) produces a PDF on your machine.

## Stage 1 — Make it correct (Week 1) — doc 03, phases B1–B2 + doc 04, phase F1

Backend contract fixes (B1.1–B1.4), report/PDF endpoints (B2.1–B2.4), frontend client alignment (F1.1–F1.2). *Two devs: one does B1–B2, the other F1 concurrently against the contract doc.*

**Exit test:** full clarify→consent→report→PDF flow works through the real UI locally, with no mocked content in the report panel.

## Stage 2 — Make it honest (Week 2) — doc 04 phase F2 + doc 03 phase B3 + security §5

Real SSE coverage and streaming report (F2.1–F2.4), config hygiene (B3), and — do it now, not later — the SSRF-guarded fetcher (`11-SECURITY-PLAN.md` §5) because the scraper is already fetching arbitrary URLs today.

**Exit test:** smoke script (write it now if you skipped ahead: B8.1) prints PASS; SSRF test suite green.

## Stage 3 — Make it yours-and-mine (Week 3) — doc 03 B4–B5 + doc 04 F3 + security §1–§4

Real Google auth, ownership checks, session-scoped SSE, rate limits, quota schema; frontend login, route protection, session resume.

**Exit test:** two different Google accounts in two browsers each see only their own sessions/events; security §1 tests green.

## Stage 4 — Make it deployable (Week 4) — doc 03 B6–B9 + doc 07 all parts

R2 storage, Docker, Alembic, CI, smoke+API tests, Sentry — then follow the deployment guide to put it on the public internet.

**Exit test:** doc 07 Part 7 production smoke test passes on your real domain. **You now have a private beta.** Start doing GTM pre-launch work (doc 09 §2) in parallel from here on — 30 min/day, non-negotiable.

## Stage 5 — Make it competitive (Weeks 5–7) — the `workers/` folder

Follow the build order in `workers/README.md`. Realistic slicing:

| Week | Worker plans | Why this order |
|---|---|---|
| 5 | W3 Research (all), W6 Section Writer S1–S4 | Evidence + accuracy = the trust story; biggest report-quality jump |
| 6 | W5 Competitor (all), W9 Export X1–X4 | Fills the weakest section; makes the artifact beautiful |
| 7 | W8 Assembler A1–A5, W6 S5 streaming, W2 Outline O1–O3 | Executive summary + coherence + adaptive outlines |

Defer to post-launch unless ahead of schedule: W1 (clarification upgrades), W4 T2–T6 (momentum/monitoring), W7 (embeddings/deep-dive), W2 O4 (editable outline), W9 X5 (DOCX).

**Exit test per week:** each worker's own testing checklist, plus the smoke script, plus one full manual report read-through — you personally read every word of one generated report each Friday. Quality regressions hide from tests; they don't hide from readers.

## Stage 6 — Make it sellable (Week 8) — doc 08 + security §6–§10

Stripe/Razorpay integration + verification matrix, hardening checklist, the full pre-launch security checklist at the end of `11-SECURITY-PLAN.md`, and the launch gate (doc 08 §5): 3 consecutive daily smoke passes, ≥ 90% completion over 20 diverse reports, billing matrix green with your own card.

**Exit test:** the doc 08 §5 launch gate — all six items.

## Stage 7 — Launch (Week 9) — doc 09 §4

The launch-week sequence: waitlist → Product Hunt → Show HN → communities. Engineering freezes except for bug fixes; your job this week is answering users within minutes and watching Sentry + the four admin stats.

## Stage 8 — The loop (Week 10 onward) — doc 09 §5–§6 (+ doc 10 if India-solo)

20% code / 80% distribution. Weekly metric loop; ship the deferred worker features (W7 deep-dive, W4 monitoring) as **paid-tier retention features** once ~20 customers exist, not before.

---

## Progress tracker (copy into an issue or notes file, tick as you go)

- [ ] Stage 0 — local PDF produced
- [ ] Stage 1 — real report through the UI
- [ ] Stage 2 — smoke PASS + SSRF green
- [ ] Stage 3 — two-account isolation verified
- [ ] Stage 4 — live on the internet (private beta)
- [ ] Stage 5w5 — research + writer upgrades shipped
- [ ] Stage 5w6 — competitor + export upgrades shipped
- [ ] Stage 5w7 — assembler + outline upgrades shipped
- [ ] Stage 6 — launch gate green
- [ ] Stage 7 — launched publicly
- [ ] First paying customer 🎉

## When things go wrong (they will)

- **Behind schedule?** Cut Stage 5 scope, never Stage 3/4/6 (security, deployability, billing correctness are not cuttable). A launch with today's report quality + the Stage 1–4 fixes is still a viable beta.
- **Blocked > 1 day on one task?** Skip it, leave a `# TODO(blocked): reason` and a note in your tracker, continue the phase, revisit Friday.
- **An AI agent produced code you don't understand?** Ask it to explain line-by-line, and re-run that task's verification plus the phase's tests before accepting. Verification steps exist precisely so you don't have to trust — you check.
