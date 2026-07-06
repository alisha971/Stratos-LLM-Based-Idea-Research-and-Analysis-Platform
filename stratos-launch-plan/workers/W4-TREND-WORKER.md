# W4 — Trend Worker: Upgrade Plan

## 1. What it does today (plain language)

While research runs, this worker (`app/workers/trend_worker.py` + `app/services/trend_service.py`) looks for "what's happening right now" around the idea: it queries Hacker News (Algolia API), GDELT (global news database), Google News RSS, and arXiv (academic papers), dedupes the results, and stores them as trend items in Postgres + Astra. The section writer sprinkles them into the report. It works and is one of the healthier workers.

**Weaknesses:** it collects items but doesn't **understand** them — no momentum ("is this topic growing?"), no sentiment, no clustering (10 headlines about the same event count as 10 trends); source set misses where consumer/builder trends actually appear (Reddit, Product Hunt, GitHub); everything is a one-shot snapshot with no way to re-run later.

## 2. Who it competes with (the quality bar)

Standalone, this is a **trend-intelligence product** — the category of **Exploding Topics, Glimpse, Treendly**, and the trend modules of CB Insights. Their bar: a trend has a **direction and magnitude** ("search volume +240% in 12 months"), not just a list of links; noise is clustered into named topics; you can subscribe to a topic and get alerts.

## 3. Feature plan (do in order)

### T1 — Source expansion (3 new, all free)

- **File:** `app/services/trend_service.py`, one fetcher per source following the existing pattern (parallel, fail-soft, capped):
  - **Reddit** — no key needed for read-only JSON: `https://www.reddit.com/search.json?q={query}&sort=top&t=year&limit=25` with a proper User-Agent. Extract subreddit, score, num_comments, created_utc.
  - **Product Hunt** — GraphQL API (free developer token) or their RSS per topic; capture product name, tagline, votes.
  - **GitHub** — repo search API (no auth for 10 req/min): `https://api.github.com/search/repositories?q={query}&sort=stars&order=desc` filtered to repos created in the last 18 months; capture stars, created_at. (Signal: builders are building here.)
- Each source contributes a typed `source` field on `TrendItem` so downstream can weight them.

### T2 — Google Trends momentum (the headline feature)

- Add `pytrends` (unofficial Google Trends client — wrap every call in try/except, it breaks occasionally; fail-soft).
- For the idea's 3 main keywords (ask the LLM to pick them from the clarified summary): fetch 5-year interest-over-time, compute `momentum = (mean of last 12 weeks) / (mean of weeks 13–64)` → label `exploding (>2.0) / rising (1.3–2.0) / stable (0.8–1.3) / declining (<0.8)`.
- Store as a special `TrendItem` of type `momentum`; the section writer's trend section leads with it ("Search interest in X has risen ~2.4× over the past year").

### T3 — Clustering + naming

- After collection, embed item titles (reuse W7's embedding function once it exists; until then use a cheap LLM grouping call: "group these 60 titles into ≤ 8 topics, return JSON `{topic_name: [indices]}`").
- Store `cluster_name` on items. The report then says "3 dominant themes: X (14 signals), Y (9), Z (5)" instead of dumping headlines — this is the single biggest perceived-quality jump.

### T4 — Signal scoring

- Per item: `signal_score = source_weight × engagement_norm × recency_decay` where source_weight (HN 1.0, GitHub 0.9, ProductHunt 0.9, Reddit 0.7, GDELT/news 0.8, arXiv 0.9), engagement_norm = log-scaled points/stars/votes normalized 0–1 within the batch, recency_decay = 1.0 (<30 days), 0.7 (<90), 0.4 (<365), 0.2 (older).
- Keep top 25 by score; the rest are stored but flagged `below_threshold` (don't feed them to the writer).

### T5 — Sentiment tag (cheap, optional)

One batched LLM call over the top-25 titles/snippets → per item `sentiment: positive|neutral|negative|concern` (a "concern" tag on regulatory/backlash items is genuinely useful in reports). Store on the item.

### T6 — Re-run / monitoring mode (the retention feature — see India playbook churn note)

- Add a Celery beat task `refresh_trends(report_id)` that re-runs T1–T5 for a saved report's keywords and computes deltas vs the previous run ("new this month", "momentum change").
- Expose `POST /reports/{id}/watch` (paid-tier flag on the user) that enables monthly refresh + an email via Resend with the delta summary. This turns a one-shot report tool into a subscription-worthy monitor.

### T7 — Standalone product mode (optional)

`POST /v1/trends` with `{topic}` → `{momentum, clusters, top_signals, sentiment_mix}`. That response IS an Exploding-Topics-lite API. Add API-key auth + metering as in W3.

## 4. Testing checklist (run all before production)

1. **Fetcher unit tests** (mock HTTP): each of the 7 sources returns normalized `TrendItem`s; each source failing alone → others still saved, `trend_ready` still emitted with a `sources_failed` list in the payload (add it, update the contract doc).
2. **Rate-limit courtesy:** GitHub fetcher makes ≤ 2 calls/run; Reddit sends a custom User-Agent (assert header in the mock) — violating either gets you IP-banned in production.
3. **Momentum math unit test:** synthetic pytrends series (flat, doubling, halving) → correct labels; pytrends raising an exception → momentum item absent, run continues.
4. **Clustering test:** 30 synthetic titles about 3 obvious topics → ≤ 8 clusters, and the 3 planted topics each recovered with ≥ 70% of their members (LLM-judge check is acceptable).
5. **Scoring test:** a 10-day-old 500-point HN item must outrank a 2-year-old 40-point Reddit post.
6. **End-to-end eval (manual):** run for "GLP-1 weight-loss drugs" and "AI coding agents" — momentum must come out `rising`/`exploding` for both (they are); clusters must be recognizably real themes. Paste outputs in the PR.
7. **Timeout discipline:** total trend phase ≤ 60 s p50; each source hard-capped at 15 s.
8. **Regression:** pipeline smoke passes; section writer still renders trend content.
