# W3 — Research Worker: Upgrade Plan

> **Highest-leverage worker in the system.** Every downstream section is only as good as the evidence gathered here. If you upgrade only one worker, upgrade this one.

## 1. What it does today (plain language)

Given the approved idea summary, this worker (`app/workers/research_worker.py` + `app/services/research_service.py`) asks the LLM to invent search queries, runs them through **SerpAPI** (Google web/news/patents), scrapes the result pages with `requests` + BeautifulSoup, cleans the text, removes duplicate URLs, and saves "evidence" snippets to Postgres and Astra DB.

**Weaknesses:** one search provider (expensive, single point of failure); scraping with bare `requests` fails on ~30–50% of modern sites (JS-rendered pages, bot walls); no notion of source quality (a Reddit comment and a Statista page weigh the same); no recency preference; snippets are shallow (search-result descriptions rather than real page content when scraping fails); repeated runs re-fetch everything (no cache).

## 2. Who it competes with (the quality bar)

Standalone, this is a **research/search API for AI** — the exact category of **Tavily, Exa, Serper, Brave Search API, Perplexity's Sonar API**, and the retrieval layer inside Deep Research products. Their bar:

- Answer-ready content extracts, not just links (Tavily returns cleaned page content).
- Sub-5-second query latency, aggressive caching.
- Source diversity and spam filtering.
- Cost: fractions of a cent per query.

## 3. Feature plan (do in order)

### R1 — Provider abstraction layer

- **File:** new `app/services/search_providers.py` defining `SearchProvider` (protocol: `search(query, kind: web|news, count) -> list[SearchResult]` where `SearchResult = {url, title, snippet, published_at?, position}`).
- Implement three: `SerpApiProvider` (move existing code), `SerperProvider` (serper.dev — ~10× cheaper), `BraveProvider` (free tier 2k/mo). Selection by env `SEARCH_PROVIDER=serpapi|serper|brave`, with `SEARCH_FALLBACK_PROVIDER` tried automatically on error/quota (wrap in try/except, log which provider served each query).
- **Why first:** everything after this becomes provider-independent, and it cuts your biggest bill immediately.

### R2 — Real content extraction

- Add `trafilatura` to requirements (best-in-class article text extractor, no browser needed). Replace the BeautifulSoup scrape path: `trafilatura.fetch_url` + `extract` with `include_comments=False`. Keep the existing cleaner as fallback.
- Set a hard budget: max 3 s connect / 8 s read timeout per page, max 15 pages scraped per query batch, max 5,000 chars kept per page (take the first 5,000 after extraction — intros carry the thesis).
- Mark each evidence row with `extraction_quality: full|snippet_only` so the ranker (R4) can prefer full extractions.
- **SSRF guard (security-critical, see `../11-SECURITY-PLAN.md` §5):** before fetching any URL, resolve the hostname and refuse private/reserved IP ranges, non-http(s) schemes, and ports other than 80/443.

### R3 — Query planning upgrade

- Current: LLM invents N queries in one shot. Upgrade to **typed query slots** so coverage is systematic. Prompt returns exactly: 2 market-size queries ("{industry} market size 2026", "{industry} TAM forecast"), 2 competitor queries, 2 customer-pain queries, 1 pricing query, 1 regulation query (only if outline includes the regulatory section — read the outline's `evidence_hints` from W2 task O5), 1 recent-news query with date operator.
- Add negative keywords the LLM must append when the idea is ambiguous (e.g. idea "apple harvesting robot" → `-iphone -mac`).
- Deduplicate queries by normalized text before spending provider credits.

### R4 — Source credibility scoring

- **File:** extend `app/services/evidence_ranker.py`. Add a `credibility` component (0–1) to each evidence score:
  - Domain tier list (a simple dict in code, ~60 entries): tier A (1.0) — gov/edu/major stats providers (statista, census.gov, oecd, worldbank), major business press (reuters, bloomberg, ft, wsj); tier B (0.7) — techcrunch, industry press, crunchbase, major consultancies; tier C (0.4) — general blogs, medium; tier D (0.1) — forums, quora, pinterest, content farms (maintain a small blocklist too).
  - Recency boost: +0.2 if `published_at` within 18 months (news results carry dates; pages often expose `article:published_time` meta — trafilatura extracts it).
  - Final rank = existing keyword score × 0.5 + credibility × 0.35 + recency × 0.15.
- Store the credibility score on the evidence row; the section writer's citation list can then show a "high-confidence source" badge later.

### R5 — Caching + budget control

- Redis cache keyed by `sha1(provider + query)`, value = serialized results, TTL 7 days. Check before any provider call. (Two users researching "pet insurance" within a week share the search spend.)
- Per-session budget guard: max 12 provider queries and 40 scraped pages per report (constants in config). When exhausted, proceed with what exists — never fail research over budget.

### R6 — Coverage self-check (the accuracy multiplier)

- After evidence is saved, one LLM call: given the outline's sections and the top-30 evidence titles/snippets, return `{"gaps": [{"section": "...", "missing": "market size numbers"}]}`. If gaps are non-empty and the query budget allows, generate up to 3 targeted follow-up queries for the worst gap and run one more search round. This "reflect and re-search" loop is precisely what makes Deep Research products feel thorough.

### R7 — Standalone product mode (optional)

`POST /v1/research` with `{topic, depth: quick|standard|deep}` → `{evidence: [{url, title, extract, credibility, published_at}], coverage_report}`. This is literally a Tavily competitor for the niche of business/market questions. Requires: API-key auth (reuse doc 08 patterns), per-key metering.

## 4. Testing checklist (run all before production)

1. **Provider unit tests** (`tests/test_search_providers.py`): mock HTTP for each provider → normalized `SearchResult` shape identical across all three; provider failure → fallback provider called; both fail → empty list + `research_failed` NOT emitted if some other queries succeeded.
2. **SSRF tests (release blocker):** `fetch` must refuse: `http://169.254.169.254/`, `http://localhost:8000`, `file:///etc/passwd`, `http://10.0.0.5/`, a hostname DNS-resolving to a private IP (mock the resolver). All five must be blocked and logged.
3. **Extraction test:** run extraction against 10 live URLs listed in the test file (mix: news article, blog, docs page, JS-heavy site). Target: ≥ 7/10 yield `extraction_quality=full` with > 500 chars. Paste the table of results in the PR.
4. **Ranker unit tests:** statista.com snippet must outrank a quora.com snippet with identical text; an 18-month-old dated article outranks an undated one at equal tier.
5. **Cache test:** same query twice → second call makes zero provider HTTP requests (assert via mock call count); TTL respected.
6. **Budget test:** configure budget to 3 queries → worker stops at 3, completes normally, logs "budget exhausted".
7. **End-to-end quality eval (manual, the important one):** run research for 3 ideas ("EV charging for apartment buildings", "AI legal-doc review for Indian SMBs", "premium matcha D2C in the US"). For each, a human or judge-LLM reviews the top-15 evidence rows: ≥ 80% on-topic, ≥ 5 tier-A/B domains, ≥ 3 items ≤ 18 months old, zero blocklisted domains. Paste the scorecards in the PR.
8. **Latency:** full research phase ≤ 90 s p50 for `standard` depth (time it in the smoke script).
9. **Regression:** pipeline smoke passes; `searching_sources`/`research_done` payloads unchanged.
