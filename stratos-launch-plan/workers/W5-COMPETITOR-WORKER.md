# W5 — Competitor Worker: Build Plan (from zero)

## 1. Current state (plain language)

**This worker does not exist.** There is no `app/workers/competitor_worker.py`. Everything around it is waiting for it: the orchestrator has a commented-out dispatch line, Postgres has empty `competitors` / `competitor_features` tables, Astra has a `competitor_insights` collection that the section writer reads (and always finds empty), and every report ships a "Competitor Landscape" section written from generic search evidence. This is the report's weakest section today — and the section users flip to first.

## 2. Who it competes with (the quality bar)

Standalone, this is a **competitor-intelligence product** — the category of **Crayon, Klue, Kompyte**, and the free tier of similar tools. Their bar for a landscape snapshot: correctly **named** competitors (not hallucinated), each with what they do, who they serve, pricing if public, and a positioning takeaway. Users forgive missing data; they do not forgive invented companies. **Accuracy rule for everything below: no company enters the report without a live URL that was actually fetched.**

## 3. Feature plan (do in order)

### K1 — Worker skeleton + orchestration

- **Files:** new `app/workers/competitor_worker.py` (`run_competitor(report_id)` Celery task, retry policy copied from trend worker), new `app/services/competitor_service.py`.
- Uncomment the dispatch in `orchestrator_service.py` (it currently runs research + trend in parallel — add competitor as a third parallel branch). Extend the section-writing gate (main plan B2.4) to also wait for `competitor_ready` OR a 120 s timeout.
- Events: `scanning_competitors`, `competitor_ready` (`{session_id, report_id, competitors_count}`), `competitor_failed` (fail-soft: pipeline continues without it). Add all three to `../05-INTEGRATION-CONTRACT.md` and the frontend event union.

### K2 — Competitor discovery (two independent channels, then merge)

- **Channel A — LLM candidates:** prompt with the clarified summary: "List up to 10 real companies competing with this idea. Return JSON `[{name, url, one_liner}]`. Only companies you are confident actually exist." Treat these as **unverified candidates**.
- **Channel B — search discovery:** via the W3 provider layer, run 3 queries: `"{category}" competitors`, `best {category} tools/companies {year}`, `{category} alternatives`. Extract company names + URLs from result titles/snippets with one LLM extraction call.
- Merge by normalized domain; every candidate must pass **verification**: fetch its homepage (same SSRF-guarded fetcher as W3-R2, 8 s timeout). HTTP 200 + extractable text → verified; anything else → dropped and logged. **Verification is the anti-hallucination wall — never skip it.**

### K3 — Per-competitor profiling

For each verified competitor (cap: 7), from the fetched homepage text (first 5,000 chars) + one extra fetch of `/pricing` if linked:

- One LLM call per competitor returning JSON: `{name, tagline, target_customer, key_features: [3-5], pricing_model: subscription|onetime|freemium|enterprise|unknown, pricing_signal: "e.g. from $29/mo" | null, differentiators: [1-3]}`.
- Rule in the prompt: "Use ONLY the provided page text. If pricing is not in the text, return null — do not guess." Validate: any field whose value doesn't appear supported by the source text gets nulled by a cheap self-check pass ("is each claim supported by the text? fix JSON").
- Persist: Postgres `Competitor` + `CompetitorFeature` rows; Astra `competitor_insights` docs shaped exactly as the section writer's existing reader expects (check `astra_evidence_repository.fetch_competitor_insights` for the expected fields — match them, don't invent a new shape).

### K4 — Landscape synthesis

One final LLM call over all profiles → `{positioning_axes: {x: "price", y: "target size"}, clusters: [{label, members}], whitespace: "one paragraph on the gap this idea could fill", threat_level: low|medium|high with reason}`. Store as a special `competitor_insights` doc of type `synthesis`. The section writer's competitor section leads with the whitespace paragraph — that's the "analyst insight" moment of the whole report.

### K5 — Funding/size enrichment (best-effort, optional)

One news query per competitor (`"{name}" funding OR raised`) through the cached W3 provider; if a result title/snippet contains a funding amount, store it as `funding_signal` with the source URL. No Crunchbase paywall dependency. Skip silently when nothing is found.

### K6 — Standalone product mode (optional)

`POST /v1/competitors` with `{product_description}` → the K2–K4 output. This is a "competitor landscape API" — genuinely sellable to sales-enablement and pitch-deck tools. API-key auth + metering as in W3/W4.

## 4. Testing checklist (run all before production)

1. **Verification wall (release blocker):** feed the merger a fake candidate (`name: "Blorptech AI", url: "https://blorptech-definitely-fake-9x7.com"`) → must be dropped; a real one (`https://www.notion.com`) → must pass. Assert the fake never reaches Postgres/Astra.
2. **Fetcher SSRF tests:** same 5 cases as W3 checklist item 2 (private IPs, localhost, file://) — all blocked.
3. **Profiling grounding test:** give the profiler a homepage text that contains NO pricing → `pricing_signal` must be null (run 3 times to be sure — LLM temptation to guess is the failure mode).
4. **Shape-compat test:** after a run, the section writer's `fetch_competitor_insights` returns the docs and the competitor section renders them (assert content includes at least 2 real competitor names).
5. **Fail-soft test:** mock all searches + LLM to fail → `competitor_failed` emitted, pipeline still reaches `EXPORTED`.
6. **End-to-end eval (manual, the important one):** run for 3 ideas: "email marketing tool for Shopify stores" (crowded market — expect Klaviyo/Omnisend-class names), "AI note-taker for doctors" (mid-crowded), "underwater drone inspection for fish farms" (niche — expect ≤ 3 competitors and that's fine). Human-check every listed company is real and relevantly competitive. Target: **zero fake companies across all runs** (any fake = blocker), ≥ 80% relevance. Paste the three landscape outputs in the PR.
7. **Latency/budget:** competitor phase ≤ 120 s p50, ≤ 12 page fetches, ≤ 10 LLM calls per run.
8. **Regression:** full pipeline smoke passes with the new parallel branch and gate.
