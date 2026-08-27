# 14 — Design Decisions Record (ADR)

> Every significant design decision in Stratos — what was chosen, what the alternatives were, **why in plain language**, the trade-off knowingly accepted, and the condition under which the decision should be revisited. Decisions D1–D14 describe the code as built; D15–D22 are decisions made in the launch/worker plans (designed, being built).
>
> Why this doc exists: six months from now, someone (possibly you) will look at a choice and think "that's dumb, I'll change it" without knowing why it was made. This file is the defense against re-fighting settled battles — and the honest list of which battles *should* be re-fought, and when.

Format per decision: **Chose / Instead of / Why / Trade-off accepted / Revisit when.**

---

## Architecture

### D1 — Task pipeline on Celery + Redis, not in-request processing
- **Chose:** every pipeline stage is a Celery task executed by separate worker processes.
- **Instead of:** doing the work inside HTTP request handlers, or FastAPI `BackgroundTasks`.
- **Why:** a report takes minutes and calls flaky external services. HTTP requests time out in seconds; background tasks inside the API process die with the process and can't scale independently. Celery gives retries, concurrency control, and lets us scale workers without scaling the API.
- **Trade-off:** operational complexity — two process types, a broker, "where did my task go" debugging.
- **Revisit when:** never, realistically — this is load-bearing. The broker itself could migrate (see D22).

### D2 — Event-driven choreography with a centralized orchestrator brain
- **Chose:** workers publish events to Redis pub/sub; one `OrchestratorService` (fed by a listener) makes ALL transition decisions.
- **Instead of:** (a) pure choreography — each worker directly triggers the next; (b) a static Celery chain/chord; (c) a workflow engine (Temporal, Airflow, Prefect).
- **Why:** (a) scatters "what happens next" across nine files — debugging becomes archaeology. (b) can't express runtime fan-out (N sections decided by the outline) or our fan-in barrier cleanly. (c) is heavy machinery for one linear state machine — and framework abstractions would sit exactly where our product differentiates (validation, citation contracts). One class, fully understood, beats a framework partially understood.
- **Trade-off:** the orchestrator is a coordination hotspot, and pub/sub is fire-and-forget (see D4's mitigation).
- **Revisit when:** pipeline definitions multiply (multiple report types with different DAGs) or durable human-in-the-loop timers proliferate — that's the Temporal trigger condition.

### D3 — Pipeline state lives in Postgres rows, not in memory
- **Chose:** the session/report status column IS the state machine; every handler re-reads, checks, transitions, commits.
- **Instead of:** in-memory state, Redis-held state, or workflow-engine state.
- **Why:** any process can crash at any time; a DB row survives everything and every process can read it. It also makes state queryable ("show me all stuck sessions") with plain SQL.
- **Trade-off:** every transition costs a DB round-trip; two rapid transitions produce two commits (cosmetic).
- **Revisit when:** transition volume becomes a measured bottleneck (it won't at any plausible scale for this product).

### D4 — Redis pub/sub (fire-and-forget) for events, accepted knowingly
- **Chose:** plain pub/sub channel `stratos_events` for worker→orchestrator and →SSE events.
- **Instead of:** Redis Streams (durable, consumer groups, replay) or a real message queue (RabbitMQ topics, Kafka).
- **Why:** pub/sub is ~20 lines and zero new infrastructure. The loss window (event published while the listener is down) is tiny at one API instance, and the planned stuck-session sweeper bounds the damage of a lost event.
- **Trade-off:** lost events are possible; no replay; every subscriber sees everything.
- **Revisit when:** running >1 API instance in earnest, or when a lost-event incident actually happens. The upgrade is Redis Streams + consumer group — designed, deliberately deferred.

### D5 — Two Redis logical DBs: broker (0) and events (1)
- **Chose:** separating the command plane (Celery tasks) from the event plane (pub/sub) by logical DB.
- **Why:** bursts on one plane can't starve the other; each can be reasoned about (and later migrated) independently. Costs nothing.
- **Trade-off:** none meaningful.
- **Revisit:** if planes move to different technologies (D4/D22), this separation is what makes that cheap.

### D6 — SSE for progress streaming, not WebSockets
- **Chose:** Server-Sent Events (`EventSource`) bridging the Redis channel to the browser.
- **Instead of:** WebSockets, or polling.
- **Why:** the flow is strictly server→client; SSE is plain HTTP (no upgrade handshake, friendlier to proxies), auto-reconnects natively, and is a fraction of the implementation surface. Polling would either lag the "live typing" effect or hammer the API.
- **Trade-off:** no client→server channel (we don't need one — REST covers it); `EventSource` can't set headers, forcing the token-in-query-param compromise (see D14).
- **Revisit when:** a genuinely bidirectional feature appears (collaborative editing). Deep-dive Q&A does NOT require it (request/response fits REST).

### D7 — Events are notifications; data is fetched via REST
- **Chose:** SSE payloads say *what happened* (small); the report content is fetched from Postgres through REST endpoints. (Exception: `section_chunk` carries text deltas — the live-typing effect is the product's wow moment and re-fetching per token would be absurd.)
- **Instead of:** shipping full state in every event.
- **Why:** recoverability — a client that disconnects re-fetches state and resubscribes, nothing is lost; events stay cheap; the DB remains the single source of truth.
- **Trade-off:** one extra REST call on certain transitions.
- **Revisit:** no.

## Data

### D8 — Polyglot persistence: Postgres + Astra with strict role separation
- **Chose:** Postgres = relational system of record (users, sessions, sections, chunks, citations, sources); Astra DB = bulky semi-structured evidence (raw scraped text ≤50k chars, ranked bundles, trend items), and the future vector index.
- **Instead of:** everything in Postgres (JSONB + pgvector), or everything in a document store.
- **Why:** citations genuinely need joins and integrity (citation → source → URL is the product's trust chain); raw evidence genuinely doesn't (write-heavy, schema-loose, never joined). Astra's free tier also gives a vector store for free when W7 lands.
- **Trade-off:** two stores to operate; honestly, Postgres JSONB + pgvector could carry the whole MVP. Astra was partly a learning/ecosystem choice — which is why it was made **fail-soft** rather than load-bearing (D9). An implementer who hates the second store can collapse it into Postgres without violating the architecture; the repository class is the seam.
- **Revisit when:** operating two stores costs more attention than it saves, or vector volume justifies a dedicated choice.

### D9 — Fail-soft layering: mandatory spine, optional enrichment
- **Chose:** the pipeline hard-requires only Postgres + Redis + the LLM. Astra, each SERP engine, each trend feed, and every planned enrichment (momentum, sentiment, synthesis, bridges) degrade to fallbacks or skips, and the degradation is **recorded in data** (`source_mode: postgres_fallback`, `sources_failed`, `summary_skipped`).
- **Instead of:** fail-fast (any dependency error kills the run).
- **Why:** the product promise is "you get a report", not "you get a report if six third parties are all up". Recording degradation keeps runs diagnosable after the fact — silent degradation would poison quality debugging.
- **Trade-off:** users can receive a quietly-worse report; mitigated by the planned `quality_warning` surfacing (W8-A6).
- **Revisit:** never the principle; individual components move between spine and enrichment as the product matures.

### D10 — Idempotency by convergent writes, not exactly-once machinery
- **Chose:** Celery's at-least-once delivery, with handlers that converge on replay: delete-before-insert (outline sections, section chunks/citations), dedupe-before-store (research URLs), DB-count-based fan-in barrier.
- **Instead of:** distributed locks, task deduplication tables, or an exactly-once workflow engine.
- **Why:** exactly-once is a distributed-systems tarpit; convergent writes achieve the same end state with code a junior can verify by reading. The fan-in barrier as a DB count (not an in-memory latch) is the same philosophy: crash-safe because it's recomputed, not remembered.
- **Trade-off:** replays do redundant work (acceptable); delete-before-insert briefly windows empty state (invisible behind the state machine's gates).
- **Revisit when:** a workflow needs cross-worker transactions (none does; the design avoids creating one).

## AI / RAG

### D11 — Fixed pipeline DAG; the model never chooses the control flow
- **Chose:** the stage sequence is hardcoded; LLMs fill parameterized slots (queries, drafts, judgments) inside deterministic stages. Agentic loops exist but are bounded with deterministic termination (confidence threshold + question cap; one repair retry; one re-search round).
- **Instead of:** an autonomous agent that plans its own research strategy per idea.
- **Why:** the product sells *verifiability at predictable cost*. A fixed DAG gives bounded spend per run, debuggable failures ("it broke at research" vs "the agent wandered"), and consistent output shape. Every bounded loop was chosen precisely where iteration adds accuracy without unbounding cost.
- **Trade-off:** less adaptivity — a thin-evidence niche idea gets the same strategy as a mainstream one (partially mitigated by W3-R6's single reflection round and W6-S4's honesty mode).
- **Revisit when:** evidence shows fixed strategy is the quality bottleneck AND per-run budget enforcement is mature enough to cage an agent. Not before both.

### D12 — Deterministic validators as the floor; LLM judges only on top
- **Chose:** all format/integrity checking (citation markers, chunk sequencing, schema shapes, numeric presence) is regex-and-set-logic code. LLM judgment is reserved for what code cannot check (claim entailment, coverage) and is itself bounded and fail-soft.
- **Instead of:** LLM-as-judge for everything.
- **Why:** a deterministic critic cannot be sweet-talked by the generator, costs nothing, and never has a bad day. LLM-judging-LLM shares failure modes with the thing it judges — acceptable only where there is no mechanical alternative, and even then paired with deterministic double-checks (the pricing-digit check in P5, the numeric guard in W6-S3).
- **Trade-off:** deterministic checks are literal — they catch format lies, not semantic ones. Hence the layering, not a replacement.
- **Revisit:** never the principle.

### D13 — Precomputed per-section evidence bundles; lexical ranking first, vectors later
- **Chose:** after research, rank evidence per section once (keyword/credibility scoring, top-12, stable `CIT-###` markers), persist the bundle, and generate from it. No embeddings in v1.
- **Instead of:** retrieval-at-generation-time with a vector index from day one.
- **Why:** determinism and auditability — you can inspect exactly what a section was *allowed* to cite before generation ran, and repair loops don't re-rank. Lexical ranking is inspectable (every item stores its scoring `reason`) and adequate for a small per-report corpus (~40 pages) with distinct section vocabularies. Vectors are an upgrade (W7 blends 0.5 semantic + 0.3 credibility + 0.2 keyword), not a prerequisite.
- **Trade-off:** staleness within a run (late trend items miss bundles — mitigated by the B2.4 gate); and the shipped keyword vocabularies were overfit to the first test idea (a known flaw, fix specced in W2-O5) — the honest lesson: hardcoded vocabularies were the wrong *implementation* of the right *architecture*.
- **Revisit:** W7 is the scheduled revisit.

### D14 — Small fast model (Groq `llama-3.1-8b-instant`) behind validation, not a frontier model
- **Chose:** the cheapest/fastest credible model for all calls, wrapped in validate-and-repair; temperature 0.2 and JSON mode for structured outputs.
- **Instead of:** GPT/Claude-class models everywhere.
- **Why:** unit economics ($0.01–0.05 LLM cost per report → >90% margin at $19/mo) and latency (8 sections in ~4 min). The architecture is the hedge: validation with one repair retry means the model needs to be right-after-one-retry, not right-always. Where quality is measurably critical (claim auditor, executive summary, landscape synthesis), the prompt library marks those calls as first candidates for selective model upgrades — pay more only where audits show it's needed.
- **Trade-off:** more repair loops and occasionally flatter prose than a frontier model.
- **Revisit when:** audit scores identify sections where the small model persistently fails, or Groq pricing/model availability shifts. Provider routing is one file (`app/llm/client.py`) by design.

## Security & product

### D15 — JWT (HS256, symmetric) with ownership-filtered queries; 404 for others' resources *(planned: B4)*
- **Chose:** HS256 with one strong secret; every query filters by the JWT's user id; cross-user access returns 404, not 403.
- **Instead of:** RS256 asymmetric keys, sessions-in-DB, or an auth provider (Auth0/Clerk).
- **Why:** one service verifies its own tokens — asymmetric keys buy nothing until a second verifier exists. 404-not-403 avoids confirming resource existence to attackers. An auth provider is a fine alternative; Google-token-exchange was nearly free to build on what existed.
- **Trade-off:** secret rotation logs everyone out (acceptable, documented); JWTs can't be revoked before expiry (7-day cap bounds it).
- **Revisit when:** a second token-verifying service appears (→ RS256) or enterprise SSO demands arrive (→ provider).

### D16 — SSE auth token in the query string, with scheduled hardening *(planned: B4.3)*
- **Chose:** `?token=` on the SSE URL, because `EventSource` cannot set headers.
- **Instead of:** cookies-only auth (complicates the API-on-different-domain setup) or a WebSocket switch just for headers.
- **Why:** platform constraint, mitigated (HTTPS-only, short expiry) with a designed upgrade: 60-second single-use SSE tickets so the real credential never enters a URL.
- **Revisit:** the ticket upgrade is the revisit, scheduled post-launch.

### D17 — SSRF-guarded fetcher as a single chokepoint *(planned: security §5 — urgent)*
- **Chose:** one `safe_fetch` utility (scheme/port allowlist, DNS-resolve-then-check against private ranges, redirect re-checks, size/time caps) that ALL outbound page fetching must route through.
- **Instead of:** per-callsite checks, or trusting search engines to return safe URLs.
- **Why:** the scraper fetches attacker-influenceable URLs — the single most dangerous capability in the system (cloud metadata endpoints leak credentials). A single chokepoint is auditable; scattered checks rot.
- **Trade-off:** none. The shipped code lacking this is a flaw, not a decision — recorded here so nobody mistakes the current state for intent.

### D18 — Quotas as plan-gated counters returning 402; rate limits per user; one global daily circuit breaker *(planned: B5, doc 08)*
- **Chose:** `reports_used_this_month` on the user row, checked in `start_session`; slowapi per-user limits on expensive endpoints; a Redis daily counter that 503s the whole product past N sessions.
- **Instead of:** metered billing (charge per token/search), or trusting users.
- **Why:** every session costs real money (SERP + LLM); simple counters are explainable to users and implementable in a day. The circuit breaker exists because launch-day virality is exactly when an unbounded bill arrives.
- **Trade-off:** monthly-counter quotas are crude (no rollover, no bursting).
- **Revisit when:** usage patterns justify metered or credit-based pricing.

### D24 — The first message always starts the session; greetings are handled as social turns by the worker *(implemented: 2026-08-23)*
- **Chose:** `POST /orchestrate/start-session` accepts whatever the user first types (`min_length=1`), and the clarification worker's `message_intent` triage answers greetings/meta-questions as social turns. `session.idea_description` is provisional until the first `idea_content` message backfills it (reserved schema key `_idea_captured`).
- **Instead of:** (a) a frontend gate answering greetings locally with canned text — built and reverted; (b) a separate pre-session social-chat endpoint.
- **Why:** the local gate produced a visibly identical reply on every greeting ("hi" and "how are you" returned the same hardcoded line) and required a second, divergent code path. Worse, gating on *session existence* rather than message position let `"how are you"` fall through and seed a real session — and `idea_description` is user-visible, labelling the report in the reports list (`orchestrator_service.py:388`) and titling the report view (`:406`). One path, with LLM-generated social replies, removes both failure modes.
- **Why it's affordable (the analysis worth keeping — don't re-derive it):**
  - `START_SESSION_RATE` (5/hour) is consumed **once per conversation**, not per message: after message 1 a session exists, so every later message goes to `/orchestrate/clarification/chat` under `CLARIFICATION_CHAT_RATE` (60/hour). Greetings cannot exhaust the start-session limit.
  - Per-user report quota is unaffected today — `reports_used_this_month` is not implemented yet (planned B5).
  - `GLOBAL_DAILY_SESSION_CAP` (100/day) *is* consumed by a chit-chat-only conversation — one slot per conversation, bounded per user by the start-session limit. Knowingly accepted.
  - No new worker logic was needed for a social *first* message: the social branch already handles an empty schema via `_social_pivot` → `IDEA_PIVOT_QUESTION`.
- **Trade-off accepted:** abandoned greeting-only conversations leave `Session` + `Report` + `ChatMessage` rows and consume a daily-cap slot; every greeting costs one Groq clarification call instead of zero.
- **Revisit when:** (a) **B5 quota work lands — the quota must be counted at consent, not at session creation**, or greeting-only conversations will burn a paid report; (b) junk sessions or daily-cap dilution become measurable — then move `enforce_global_daily_cap()` from `start_session` to `accept_consent`, since the real spend (SERP + section LLM calls) begins at research, not clarification.

### D23 — Evaluated Scrapling (OSS scraper), deferred adoption *(considered: 2026-08-23)*
- **Chose:** keep the current scraping stack — `safe_get` (`app/utils/safe_fetch.py`, see D17) + `requests`/`httpx` + BeautifulSoup-based `clean_html()` (`app/utils/text_cleaner.py`). Do not adopt [Scrapling](https://github.com/D4Vinci/Scrapling)'s fetchers.
- **Instead of:** wiring in Scrapling, a BSD-3 scraping framework offering a much faster adaptive HTML parser (`Adaptor`), a Playwright-backed `DynamicFetcher` for JS rendering, and a `StealthyFetcher` with TLS-fingerprint spoofing, Cloudflare Turnstile bypass, and proxy rotation.
- **Why:** Scrapling's own fetchers do their own networking, which would bypass the D17 SSRF chokepoint that every internet-URL fetch is required to go through — using them as-is (or reimplementing SSRF protection around them) is nontrivial. Its anti-bot bypass features (Cloudflare evasion, TLS spoofing) exist specifically to defeat site protections, which is a legal/ToS exposure a citation-backed report product shouldn't take on for sources it doesn't control. The full fetcher install also pulls in Playwright + downloaded Chromium binaries, adding real deploy weight (bigger Docker images, a new failure mode in Celery workers) for a capability — JS rendering — the pipeline hasn't yet hit a demonstrated need for (research is SERP/feed-driven via SerpAPI/GDELT/feedparser, not deep site crawling).
- **Trade-off:** `clean_html()` stays slower than Scrapling's parser would be, and JS-only source pages continue to silently fail extraction (same as today — no regression, just no improvement).
- **Revisit when:** (a) evidence extraction throughput becomes a measured bottleneck — then adopt *only* Scrapling's `Adaptor` parser (parser-only install, no Playwright) as a drop-in for `clean_html()`, fed HTML already fetched via `safe_get`, keeping `safe_get` as the sole network path; or (b) a specific, observed pattern of citation sources failing because they're JS-rendered SPAs — then evaluate `DynamicFetcher` behind a rework that re-applies the D17 SSRF checks (validate the resolved IP before browser navigation, and on every redirect) rather than trusting Scrapling's own fetch path.

## Infrastructure

### D19 — Managed services everywhere; two deployables from one Docker image *(planned: B7, doc 07)*
- **Chose:** Vercel (frontend) + Railway/Render (API and workers as two services sharing one image, different start commands) + Neon + managed Redis + Astra + R2.
- **Instead of:** a VPS with docker-compose, or Kubernetes.
- **Why:** a one-person team should never be the on-call for Postgres. One image for API+workers guarantees code/dependency parity — the classic "worker has a different version than the API" bug becomes impossible.
- **Trade-off:** platform costs exceed a bare VPS at scale; migration lock-in is mild (everything speaks standard protocols by design).
- **Revisit when:** infra spend passes ~$500/mo — then a VPS/K8s cost analysis is worth an afternoon.

### D20 — Cloudflare R2 for exports with presigned URLs; local disk only in dev *(planned: B6)*
- **Chose:** R2 (S3-compatible) with 302-to-presigned-URL downloads; `EXPORT_STORAGE=local` flag for dev. The fast-ship plan's single-container-with-volume is an explicit documented shortcut, not the architecture.
- **Instead of:** S3 (egress fees on a product whose artifact is downloaded PDFs), serving files through the API (ties file bandwidth to API compute), or DB blobs.
- **Why:** zero egress fees fit the usage shape; presigned URLs keep the bucket private without proxying bytes.
- **Revisit:** unlikely.

### D21 — Alembic migrations from the production push, not from day one
- **Chose:** `create_tables.py` during exploration; Alembic baseline + migrations as part of productionization (B7.3).
- **Instead of:** migrations from the first commit.
- **Why (honest):** during solo exploration the schema churned daily and drop-and-recreate was faster than migration hygiene with zero users. The moment data matters (auth, billing columns), migrations become mandatory — and that's exactly where the plan puts them.
- **Trade-off:** the cutover requires one careful baseline against a clean DB.
- **Revisit:** n/a — one-way door, already scheduled.

### D22 — Monorepo: frontend + backend + all plan docs in one repository
- **Chose:** one repo (`stratos-frontend/`, `stratos-backend/`, plan folders) with one CI workflow.
- **Instead of:** separate repos per deployable.
- **Why:** the integration contract (doc 05) changes atomically with both sides in one PR — cross-repo contract drift is the #1 tax of splitting. Vercel and Railway both deploy from subdirectories without complaint.
- **Trade-off:** CI runs both sides on every push (mitigate with path filters when it annoys).
- **Revisit when:** separate teams own separate deploy cadences. Not a solo-founder problem.

---

## How to add a decision

Copy the format, number it, keep "Why" in plain language a newcomer can follow, and — the discipline that keeps this doc useful — **always fill "Revisit when" with a concrete trigger**, not "someday". A decision without a revisit condition is dogma; a decision with one is engineering.
