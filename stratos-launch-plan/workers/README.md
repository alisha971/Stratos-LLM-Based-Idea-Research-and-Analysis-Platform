# Worker Upgrade Plans — Index

This folder contains one implementation plan **per worker** in the Stratos pipeline. Each plan upgrades that worker from its current state to **market-competitive quality** — good enough that the worker could be launched as a **standalone product** on its own.

## Who these docs are for

A junior developer or a smaller AI coding model. Every plan follows the same structure so you always know where you are:

1. **What this worker does today** (plain-language, no jargon)
2. **Who it competes with** (real products in the market, and the quality bar they set)
3. **Feature plan** — numbered tasks, smallest first, each with files to touch and code-level hints
4. **Standalone product angle** — how to expose this worker as its own API/product
5. **Testing checklist** — exact steps a smaller AI model (or a human) must run and pass **before** declaring the worker production-ready

## Rules for implementing

- Do the tasks **in order**. Later tasks assume earlier ones are done.
- One task = one commit. Run the worker's testing checklist after each phase, and the full pipeline smoke test (`scripts/run_pipeline_smoke.py`, see main plan doc 03 task B8.1) before merging.
- Never change the event names or payload shapes without updating `../05-INTEGRATION-CONTRACT.md` in the same PR.
- All new external calls must have: a timeout, a retry policy, and a fail-soft path (the pipeline must survive any single provider dying).

## The workers

| Doc | Worker | Current state | Target |
|---|---|---|---|
| [W1](W1-CLARIFICATION-WORKER.md) | Clarification | Working, naive confidence scoring | Adaptive interviewer with semantic confidence |
| [W2](W2-OUTLINE-WORKER.md) | Outline | Working, but hardcodes 7 sections | Dynamic, report-type-aware outline planner |
| [W3](W3-RESEARCH-WORKER.md) | Research | Working via SerpAPI | Multi-provider research engine with credibility scoring |
| [W4](W4-TREND-WORKER.md) | Trend | Working, 4 sources | Trend intelligence with momentum scoring, 8+ sources |
| [W5](W5-COMPETITOR-WORKER.md) | Competitor | **Does not exist** | Automated competitor discovery + profiling |
| [W6](W6-SECTION-WRITER-WORKER.md) | Section Writer | Working, citation validation | Grounded writer with hallucination auditing |
| [W7](W7-EMBEDDING-WORKER.md) | Embedding | **No-op stub** | Real vector pipeline + Deep Dive Q&A |
| [W8](W8-ASSEMBLER-WORKER.md) | Assembler | Concatenates text only | Editorial pass: summary, transitions, consistency |
| [W9](W9-EXPORT-WORKER.md) | Export | Plain ReportLab PDF | Branded, charted, multi-format document engine |

## Suggested build order (if doing all of them)

Quality of the final report is dominated by **evidence quality → writing quality → presentation**. So:

1. W3 Research (better evidence lifts every section)
2. W6 Section Writer (accuracy + hallucination control — the trust story)
3. W5 Competitor (fills the weakest report section, currently empty)
4. W9 Export (what the customer actually sees and shares)
5. W8 Assembler (coherence + executive summary)
6. W2 Outline, W1 Clarification (UX quality)
7. W4 Trend (differentiation feature)
8. W7 Embedding (unlocks Deep Dive Q&A — a paid-tier feature)
