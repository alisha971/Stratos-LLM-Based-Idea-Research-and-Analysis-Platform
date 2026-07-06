# Low-Level Architecture - Workers

Perfect — here is the **complete Worker Responsibility Table** followed by **LLD (Low-Level Design) for every worker**, fully aligned with your updated architecture:

- AstraDB as vector + evidence store
- Postgres as relational metadata store
- Assembler only runs during export
- Section Writer streams inline chunks
- Redis Broker for job queues
- Redis Pub/Sub for progress events

This is a **production-quality LLD** that can be directly implemented.

---

# ⭐ **WORKER RESPONSIBILITY TABLE (MASTER TABLE)**

| Worker | Responsibilities | Inputs | Outputs | Writes To | Triggers |
| --- | --- | --- | --- | --- | --- |
| **Outline Worker** | Generate multi-section outline | report_id, idea summary | section rows | Postgres | SSE `outline_ready` |
| **Research Worker** | SERP search, scrape URLs, extract evidence | report_id, query | sources, cleaned text | AstraDB (evidence), Postgres (metadata) | SSE `research_progress`, `research_done` |
| **Trend Worker** | Fetch news, research papers, social sentiment | report_id | curated trend items | AstraDB + Postgres | SSE `trend_progress`, `trend_ready` |
| **Competitor Worker** | Competitor discovery, feature comparison | report_id | competitor insights | AstraDB + Postgres | SSE `competitor_progress`, `competitor_done` |
| **Section Writer Worker** | Generate section text + inline citations (STREAMING) | section_id, evidence bundle | chunk stream | Postgres (chunks), AstraDB (citations) | SSE `section_chunk`, enqueue embedding |
| **Embedding Worker** | Compute embedding for each chunk | chunk_id | embedding vector | AstraDB | SSE `embedding_stored` |
| **Assembler Worker** | Polish final report ONLY during export | report_id | cleaned unified report text | Postgres | triggers Export Worker |
| **Export Worker** | Produce PDF/HTML, store locally | report_id | rendered file | LocalFS + Postgres | SSE `export_ready` |

---

# ⭐ **FULL LLD (LOW-LEVEL DESIGN) FOR EACH WORKER**

Below is an engineering-grade LLD:

- Inputs
- Steps
- Outputs
- Error handling
- DB schema usage
- Inter-service interactions

This is the level of detail expected in system design interviews and PRDs.

---

# =====================================================================================

# 1️⃣ **OUTLINE WORKER — LLD**

# =====================================================================================

### **Input**

```json
{
  "report_id": "uuid"
}

```

### **Steps**

1. Load idea_summary from Postgres
    
    ```sql
    SELECT idea_summary FROM reports WHERE report_id = $1;
    
    ```
    
2. Call LLM:
    
    ```
    prompt = generate_outline_prompt(idea_summary)
    outline = llm.call(prompt)
    
    ```
    
3. Parse outline into section array.
4. Insert each section row:
    
    ```sql
    INSERT INTO sections(section_id, report_id, title, order_index)
    
    ```
    
5. Publish event:
    
    ```
    redis_pub.publish("outline_ready", report_id)
    
    ```
    

### **Output**

- Section rows in Postgres
- SSE event → frontend

---

# =====================================================================================

# 2️⃣ **RESEARCH WORKER — LLD**

# =====================================================================================

### **Input**

```json
{
  "report_id": "uuid"
}

```

### **Steps**

1. Load clarified idea summary → determine search queries.
2. Publish progress event: `searching_sources`.
3. Perform SERP queries:
    
    ```
    results = serp_api.search(query)
    
    ```
    
4. For each result:
    - Fetch webpage
    - Extract text
    - Clean + normalize content
5. Save evidence to AstraDB:
    
    ```json
    {
      "source_id": "...",
      "report_id": "...",
      "url": "...",
      "title": "...",
      "clean_text": "...",
      "metadata": {...}
    }
    
    ```
    
6. Save metadata to Postgres:
    
    ```
    INSERT INTO sources(source_id, report_id, url, title)
    
    ```
    
7. Publish `research_done`.

### **Output**

- Evidence in Astra
- Metadata in Postgres

---

# =====================================================================================

# 3️⃣ **TREND WORKER — LLD**

# =====================================================================================

### **Input**

```json
{
  "report_id": "uuid"
}

```

### **Steps**

1. Publish: `scanning_trends`.
2. Call:
    - NewsAPI
    - Semantic Scholar API
    - Reddit/Twitter API
3. Normalize results (title, text, sentiment).
4. Write to AstraDB (trend_items collection).
5. Write reference metadata to Postgres.
6. Publish `trend_ready`.

### **Output**

- News, papers, social signals evidence

---

# =====================================================================================

# 4️⃣ **COMPETITOR WORKER — LLD**

# =====================================================================================

### **Steps**

1. Discover competitors → SERP + Product directory lookup.
2. Extract:
    - Name
    - Features
    - Pricing
    - Strengths
    - Weaknesses
3. Call LLM to generate structured competitor comparison.
4. Save raw evidence to AstraDB.
5. Save structured metadata to Postgres.
6. Publish `competitor_done`.

---

# =====================================================================================

# 5️⃣ **SECTION WRITER WORKER — LLD**

# =====================================================================================

### **Input**

```json
{
  "section_id": "uuid",
  "report_id": "uuid"
}

```

### **Steps**

1. Load section title + report summary from Postgres.
2. Load evidence bundle from Astra:
    - sources
    - trends
    - competitor insights
3. Build prompt:
    
    ```
    Write section <title> using evidence. Stream chunks.
    Include inline citations as: [CIT-n].
    
    ```
    
4. Stream LLM response chunk-by-chunk.
5. For each chunk:
    - Save chunk row into Postgres
    - Extract provisional inline citations
    - Save citation mapping to Astra
    - Publish SSE event: `section_chunk`
6. Enqueue embedding job:
    
    ```
    redis.enqueue("embedding_queue", chunk_id)
    
    ```
    

### **Output**

- Streaming chunks
- Inline citations
- Chunk rows

---

# =====================================================================================

# 6️⃣ **EMBEDDING WORKER — LLD**

# =====================================================================================

### **Input**

```json
{ "chunk_id": "uuid" }

```

### **Steps**

1. Load chunk text from Postgres.
2. Get embedding from LLM.
3. Insert into AstraDB:
    
    ```json
    {
      "chunk_id": "...",
      "vector": [...],
      "text": "...",
      "report_id": "...",
      "section_id": "...",
      "citations": [...]
    }
    
    ```
    
4. Publish `embedding_stored`.

---

# =====================================================================================

# 7️⃣ **ASSEMBLER WORKER — LLD (ONLY DURING EXPORT)**

# =====================================================================================

### **Input**

```json
{ "report_id": "uuid" }

```

### **Steps**

1. Load all sections + chunks + citations.
2. Merge into one long text.
3. Send to LLM:
    
    ```
    "Polish this content into a unified, well-organized final report.
     Do not change factual content."
    
    ```
    
4. Save polished version to Postgres:
    
    ```
    UPDATE reports SET final_text = ...
    
    ```
    

### **Output**

- Polished final report saved

---

# =====================================================================================

# 8️⃣ **EXPORT WORKER — LLD**

# =====================================================================================

### **Input**

```json
{
  "report_id": "uuid",
  "format": "PDF" | "HTML"
}

```

### **Steps**

1. Load final_text from Postgres (generated by Assembler).
2. Render PDF/HTML (WeasyPrint / wkhtmltopdf).
3. Save to LocalFS:
    
    ```
    /exports/report_<id>.pdf
    
    ```
    
4. Save export URL/path into Postgres.
5. Publish SSE event: `export_ready`.

---

# ⭐ SUMMARY TABLE (LLD Key Points)

| Worker | DB Reads | DB Writes | Calls LLM? | Calls External APIs? | Streams? |
| --- | --- | --- | --- | --- | --- |
| Outline | Postgres | Postgres | Yes | No | No |
| Research | Postgres | Astra + Postgres | Yes | Yes (SERP) | Progress only |
| Trend | Postgres | Astra + Postgres | Yes | Yes (News, Papers, Social) | Progress only |
| Competitor | Postgres | Astra + Postgres | Yes | Yes | Progress only |
| Section Writer | Postgres + Astra | Postgres + Astra | Yes (stream) | No | **Yes** |
| Embedding | Postgres | Astra | Yes | No | Progress |
| Assembler | Postgres | Postgres | Yes | No | No |
| Export | Postgres | LocalFS + Postgres | No | Renderer call | No |

---

# ⭐ If you want next:

I can generate:

### 🔸 Worker API Contracts (function signatures)

### 🔸 Redis Pub/Sub Event Schema

### 🔸 End-to-end API spec (OpenAPI format)

### 🔸 Deployment-ready architecture (Railway/Render)

### 🔸 Worker queue design + retry policy + DLQ

Just say:

**"Give API contracts"** or

**"Give Redis event schema"**

Nice — below is a thorough **Low-Level Design (LLD)** for **each worker** in the full system (no merges). For every worker I give:

- Purpose / responsibilities
- Task contract (Celery task signature + example payload)
- Inputs / outputs (DB rows / tables touched)
- Processing steps / pseudocode (clear sequence)
- Idempotency & dedupe strategy
- Retry / backoff / DLQ policy
- Scaling / resource guidance (CPU / RAM / concurrency)
- Observability & metrics to emit
- Error handling & fallbacks
- Testing checklist

This is ready for engineers to implement as independent services (Python + Celery workers calling LLM & external APIs). I assume Postgres + Milvus + Redis + S3 as earlier.

---

## 1) Outline Worker

**Purpose:** Create a multi-section outline from an idea description -> drives section jobs.

### Task contract

`tasks.generate_outline(report_id: UUID, idea_text: str, options: dict)`

**Example payload**

```json
{
  "report_id": "r_uuid",
  "idea_text": "AI-powered personal finance assistant for gig workers",
  "options": {"depth": 6, "style": "investor_pitch"}
}

```

### Inputs / Outputs

- Inputs: `reports(report_id)`, `sessions(session_id)` for context
- Writes: `report_sections` rows (one per heading), update `reports.status`
- Emits event: `outline_ready` via RedisPub

### Processing steps (pseudocode)

```
load report metadata
build prompt: idea_text + few-shot outline examples + options
call LLM (system prompt: produce headings + short description)
validate outline: headings non-empty, <= N
save sections to DB: INSERT report_sections (status=pending)
publish "outline_ready"
enqueue section jobs (or notify orchestrator)

```

### Idempotency

Use `job_id = hash(report_id, 'outline')`. If sections exist and checksum of idea_text matches saved checksum, skip re-run.

### Retry / Backoff

- Retries: 3, exponential backoff (2s, 4s, 8s)
- On repeated failure -> set `reports.status = 'outline_failed'` and push to DLQ.

### Scaling / Resources

- CPU light, bursty IO to LLM.
- Recommend: 0.5–1 vCPU, 512–1024MB RAM.
- Concurrency: 2–4 workers.

### Observability / Metrics

- `outline_jobs_started`, `outline_jobs_succeeded`, `outline_jobs_failed`, `outline_duration_ms`
- log LLM token counts, prompt+response sizes

### Error handling & fallbacks

- If LLM returns bad format -> retry with stricter prompt template.
- If LLM unavailable -> mark partial outline using template fallback (e.g., common headings).

### Tests

- Unit: prompt formation / validation
- Integration: mock LLM returns -> DB writes
- Idempotency tests (re-run same job)

---

## 2) Research Worker (SERP + Scraper)

**Purpose:** Discover and fetch raw sources (web pages) for a report or section.

### Task contract

`tasks.run_research(report_id: UUID, query_list: [str], options: dict)`

**Example payload**

```json
{
  "report_id":"r_uuid",
  "query_list":["ai personal finance gig workers", "gig economy budgeting apps"],
  "options":{"max_urls":50,"timeout_sec":30}
}

```

### Inputs / Outputs

- Reads: `reports`, optional `report_sections`
- Writes: `sources` rows (url, title, snippet, fetched_at), `worker_jobs` logs
- Emits: `research_done` event

### Processing steps

1. For each query: call Search API (Serp/Bing) and collect top N results.
2. De-duplicate URLs.
3. For each URL: schedule scraping (HTTP GET) with robots.txt check, user-agent, timeouts.
4. Extract main content (boilerplate removal), title, published date.
5. Compute `domain_score` (simple heuristic) and `snippet`.
6. Insert or upsert into `sources`.
7. Return top M sources to orchestrator.

### Idempotency & Dedupe

- Content hash (sha256) of cleaned text stored; upsert by canonical URL or content_hash.
- `source.fingerprint = hash(url_normalized)` to prevent re-insert.

### Retry / Backoff

- Search API: 3 retries, exponential backoff.
- Scraper: 2 retries for transient errors; 429 -> exponential with larger backoff; blocked -> record snippet only.

### Scaling / Resources

- CPU moderate, network IO heavy.
- Recommend: 1–2 vCPU, 2–4 GB RAM.
- Concurrency: 10–50 concurrent scraper threads (use async HTTP client).

### Observability / Metrics

- `search_api_calls`, `search_api_errors`, `pages_scraped`, `pages_failed`, `avg_scrape_latency_ms`, `sources_inserted`
- track per-domain failure rate

### Error handling & fallbacks

- If scraping fails, save SERP snippet as fallback.
- If site blocks scraping, mark `sources.blocked = true`.

### Tests

- Mock search API responses, assert `sources` rows created
- Scraper unit tests for HTML extraction and noise removal
- Respect robots.txt test cases

---

## 3) Trend Worker (News + Papers + Social)

**Purpose:** Gather news, recent research papers, and social signals for a topic.

### Task contract

`tasks.run_trend_scan(report_id: UUID, topic_keywords: [str], options: dict)`

**Example payload**

```json
{
 "report_id":"r_uuid",
 "topic_keywords":["gig worker finance","microtasks payments"],
 "options":{"days":90,"max_news":30,"max_papers":20}
}

```

### Inputs / Outputs

- Reads: `reports`, `sessions` (for geographic or timeframe)
- Writes: `sources` (tagged as news/paper/social), additional `trend_items` (optional table)
- Emits: `trend_ready`

### Processing steps

1. Build queries for news, papers, social (LLM may expand keywords).
2. Call News API (Serp) -> collect urls -> feed to Scraper (or save SERP snippet).
3. Call Paper APIs (Semantic Scholar, arXiv) for metadata -> save to `sources` (paper type).
4. Pull social posts (Reddit, X via API or RSS) -> extract top posts -> store as `sources` or `social_snippets`.
5. Score relevance & recency, compute `trend_score`.
6. Save entries and publish event.

### Idempotency & Dedupe

- Use canonical IDs for papers (arXiv ID / DOI) to avoid duplication.
- For social posts, unique post id.

### Retry / Backoff

- Similar to Research Worker but with more conservative rate limits for social APIs.

### Scaling / Resources

- Moderate CPU; IO bound.
- 1–2 vCPU, 1–2 GB RAM.
- Concurrency tuned to API rate limits.

### Observability / Metrics

- `news_items`, `paper_items`, `social_items`, `trend_scan_duration_ms`, `rate_limit_hits`

### Error handling & fallbacks

- If paper API fails, fallback to arXiv or CrossRef.
- If social API unavailable, rely on RSS or skip.

### Tests

- Paper metadata parsing tests
- Social snippet extraction tests

---

## 4) Competitor Analysis Worker

**Purpose:** Discover competitors, extract feature lists, pricing, and produce structured competitor profiles.

### Task contract

`tasks.run_competitor_analysis(report_id: UUID, query: str, options: dict)`

**Example payload**

```json
{
 "report_id":"r_uuid",
 "query":"alternatives to Personal Finance App X",
 "options":{"max_competitors":10}
}

```

### Inputs / Outputs

- Reads: `reports`, `sources` (for competitor pages)
- Writes: `competitor_profiles` (table), may write `sources` and `citations`
- Emits: `competitor_done`

### Processing steps

1. Use Search APIs to find product pages, review pages, app store entries.
2. Scrape product pages for features, pricing, screenshots.
3. Summarize pros/cons via LLM (short prompt).
4. Generate structured profile JSON: `{name, features[], pricing[], pros[], cons[], popularity_metrics}`.
5. Save `competitor_profiles` and link to `sources`.

### Idempotency & Dedupe

- Deduplicate by domain + product slug.
- `competitor_profile.fingerprint = hash(name + domain)`

### Retry / Backoff

- Standard 3 retries for network; LLM retries as needed.

### Scaling / Resources

- Moderate CPU; LLM calls per competitor.
- 1–2 vCPU, 1–3 GB RAM.
- Concurrency 2–8 depending token budget.

### Observability / Metrics

- `competitors_found`, `competitor_profiles_created`, `avg_profile_generation_time_ms`

### Error handling & fallbacks

- If scraping fails, use SERP snippets or review aggregators.
- If LLM fails to produce structured JSON, run a re-format step.

### Tests

- End-to-end competitor detection tests (mock search + scraper)
- LLM output schema validation

---

## 5) Section Writer Worker

**Purpose:** Core LLM heavy worker — generates chunked section text grounded in provided citations/sources; streams chunks.

### Task contract

`tasks.generate_section(section_id: UUID, report_id: UUID, options: dict)`

**Example payload**

```json
{
 "section_id":"s_uuid",
 "report_id":"r_uuid",
 "options":{"max_tokens":1500,"chunk_size":400}
}

```

### Inputs / Outputs

- Reads: `report_sections`, `sources`, `citations`, `competitor_profiles`, `trend_items`
- Writes: `report_chunks`, update `report_sections.status`
- Emits: `chunk_ready` events for each saved chunk.

### Processing steps

1. Load section prompt context (section heading, existing citations).
2. Select top N supporting `sources` and snippets (by relevance_score).
3. Construct grounding prompt:
    - system: enforce "only use provided citations"
    - provide evidence blocks with citation IDs & snippets
    - instruct streaming chunk format
4. Call LLM streaming API; as chunks arrive:
    - validate chunk length
    - save chunk to `report_chunks` with order_index
    - publish chunk event (SSE)
5. After final chunk, mark section completed.

### Idempotency & Dedupe

- Use `section_job_id = hash(section_id, report_version)`.
- If chunks already exist for section and `report.version` unchanged, skip unless forced regenerate.

### Retry / Backoff

- LLM transient errors: retry 2 times with jitter.
- If chunk stream interrupted, re-request last N tokens via `stream_resume` technique or re-generate section from last stable chunk.

### Scaling / Resources

- Very heavy LLM usage; can be scaled horizontally.
- Each worker: 2–8 vCPU, 8–32 GB RAM depending model latency.
- Concurrency: low per instance (1–4) because GPU/LLM throughput constraints.

### Observability / Metrics

- `section_jobs_started`, `section_jobs_succeeded`, `chunks_emitted`, `llm_tokens_consumed`, `chunk_save_latency_ms`, `streaming_failures`

### Error handling & fallbacks

- If insufficient citations found, either:
    - fallback: call Research Worker to get more sources, or
    - generate partial section and tag low_confidence
- Hallucination detection: ensure any factual claim has a mapped `[CIT-id]`; if not, mark sentence low confidence and optionally re-run with stricter prompt.

### Tests

- Streaming integration tests (simulate LLM stream)
- Grounding enforcement tests (LLM must reference provided citation ids)
- Failure/resume tests

---

## 6) Citation Worker

**Purpose:** Normalize, score and create canonical citation records for sources and link them to sections.

### Task contract

`tasks.extract_citations(report_id: UUID, section_id: UUID, candidate_sources: [source_id])`

**Example payload**

```json
{
 "report_id":"r_uuid",
 "section_id":"s_uuid",
 "candidate_sources":["src1","src2","src3"]
}

```

### Inputs / Outputs

- Reads: `sources`, `report_sections`, `report_chunks`
- Writes: `citations` rows, updates `sources` metadata
- Emits: `citations_ready`

### Processing steps

1. For each candidate source, fetch `clean_text`.
2. Use LLM to extract the best supporting snippet for the section claims, and to rate relevance/credibility.
3. Normalize into `citation_text` (Author/Title/Year), capture `relevance_score` and `credibility_score`.
4. Save `citations` rows linking `section_id` + `source_id`.
5. Update `sources.domain_score` if needed.

### Idempotency & Dedupe

- Create citation fingerprint `hash(source_id, section_id, snippet_hash)` to skip duplicates.

### Retry / Backoff

- LLM failures -> 2 retries, then queue manual review.

### Scaling / Resources

- Moderate LLM calls but lighter than Section Writer; 1 vCPU, 2–4 GB RAM.
- Concurrency: 5–20

### Observability / Metrics

- `citations_extracted`, `avg_relevance_score`, `citation_llm_errors`

### Error handling & fallbacks

- If LLM cannot extract snippet, fallback to SERP snippet and mark low_relevance.

### Tests

- Citation formatting tests
- Relevance scoring regression tests

---

## 7) Embedding Worker

**Purpose:** Create embeddings for `report_chunks` and insert into Milvus; store vector_id mapping.

### Task contract

`tasks.create_embeddings(report_id: UUID, chunk_ids: [UUID])`

**Example payload**

```json
{"report_id":"r_uuid", "chunk_ids":["ch1","ch2","ch3"]}

```

### Inputs / Outputs

- Reads: `report_chunks`
- Writes: `embeddings` rows (chunk_id, vector_id) and inserts vectors into Milvus
- Emits: `embeddings_stored`

### Processing steps

1. Batch chunk texts (batch size depending on embedding model).
2. Call embedding API to get vectors for batch.
3. Insert vectors into Milvus with metadata `{chunk_id, tenant, report_id, section_id}`.
4. Save `embeddings` rows: `vector_id` returned by Milvus.
5. Optional: compute and store `norm`.

### Idempotency & Dedupe

- Skip if `embeddings` row exists for chunk_id.
- Use batch idempotence by checking chunk list existence.

### Retry / Backoff

- Retry 3 times on network errors; if Milvus fails, leave chunks flagged for retry.

### Scaling / Resources

- CPU light; memory moderate; network & Milvus client intensive.
- 1 vCPU, 2–4 GB RAM.
- Concurrency: high (embedding calls can be batched, but rate-limited)

### Observability / Metrics

- `embedding_batches`, `vectors_inserted`, `avg_embedding_latency_ms`, `milvus_errors`

### Error handling & fallbacks

- If vector API rejects large input, reduce batch size.
- If Milvus not available, persist vectors in temporary storage and retry.

### Tests

- Batch embedding correctness
- Milvus insertion tests (mock)

---

## 8) Assembler Worker

**Purpose:** Final polish: compile sections into final report, create TOC, executive summary, and set report status to complete.

### Task contract

`tasks.assemble_report(report_id: UUID)`

**Example payload**

```json
{"report_id":"r_uuid"}

```

### Inputs / Outputs

- Reads: `report_sections`, `report_chunks`, `citations`, `sources`
- Writes: `reports.summary`, `reports.status`, optionally `report_chunks` (polished chunks)
- Emits: `report_complete`

### Processing steps

1. Load all sections and chunks in order.
2. Optionally call LLM to produce executive summary and polish transitions.
3. Validate all inline citations exist and map to `citations`.
4. Save `reports.summary`, update status to `complete`.
5. Publish `report_complete` event.

### Idempotency & Dedupe

- `assemble_job_id = hash(report_id, report_version)`. If status already `complete` and version unchanged, skip.

### Retry / Backoff

- LLM polish failures: retry 2 times with reduced token budget.

### Scaling / Resources

- Moderate: 1–2 vCPU, 2–8 GB RAM. Concurrency low (1 per report).

### Observability / Metrics

- `assembly_jobs_started`, `assembly_jobs_succeeded`, `assembly_duration_ms`

### Error handling & fallbacks

- If summary LLM fails, compile minimal summary via first sentences of sections.

### Tests

- End-to-end assemble test verifying report completeness and citation integrity

---

## 9) Export Worker

**Purpose:** Render final report (HTML -> PDF) and upload to S3; create downloadable link.

### Task contract

`tasks.export_report(report_id: UUID, format: "pdf"|"html")`

**Example payload**

```json
{"report_id":"r_uuid", "format":"pdf"}

```

### Inputs / Outputs

- Reads: `reports`, `report_sections`, `report_chunks`, `citations`, `sources`
- Writes: `exports` row with S3 URL
- Emits: `export_ready`

### Processing steps

1. Load report data, generate HTML via Jinja templates (inject CSS and images).
2. Use headless Chromium (Puppeteer) or wkhtmltopdf to render PDF.
3. Upload artifact to S3, set ACL / presigned URL.
4. Save `exports` row with `url`, `type`.
5. Publish `export_ready`.

### Idempotency & Dedupe

- If export exists for same `report_version` and type, return existing URL.

### Retry / Backoff

- Rendering errors: retry once with smaller page size or simplified template.
- S3 upload: retry 3 times.

### Scaling / Resources

- CPU and memory heavy during rendering; spawn isolated container per job.
- Recommended: 2–4 vCPU, 4–8 GB RAM (or use serverless rendering service)
- Concurrency: 1–2

### Observability / Metrics

- `exports_created`, `export_duration_ms`, `export_size_bytes`, `render_errors`

### Error handling & fallbacks

- If PDF render fails, deliver HTML only and mark export status accordingly.

### Tests

- Rendering unit tests for template correctness
- S3 upload integration tests

---

## Cross-Worker Concerns (common rules)

### Task IDs & Tracing

- Every task includes `trace_id` inherited from API request.
- Propagate trace via logs and metrics.

### Job metadata table

`worker_jobs` to track job_type, status, started_at, finished_at, error_message, trace_id.

### Security

- Workers must validate that report/session IDs are for the correct tenant (multi-tenancy).
- Do not store tokens in logs.
- Sanitize scraped HTML before storing.

### Concurrency and Rate-limits

- Central rate-limiter per external API (search, social, LLM).
- Token budget accounting per user / tenant: orchestrator checks before scheduling heavy LLM tasks.

### DLQ and Manual Recovery

- Failed tasks beyond retries go to DLQ; include `job_id`, `payload`, `error`. Create a small admin UI to replay jobs after fix.

### Monitoring & Alerts

- Alert on: DLQ spike, high task failure rates (>5% 1h), Redis queue length > threshold, Milvus unavailable, LLM rate-limit errors.

### DevOps & Deployment

- Use container images with pinned base.
- Each worker type runs in its own auto-scale group; use horizontal pod autoscaler with CPU/queue length metric.
- Use separate logging index streams per worker type for easier triage.

---

## Sample Celery Task Signatures (Python-like)

```python
# outline
@app.task(bind=True, max_retries=3)
def generate_outline(self, report_id, idea_text, options): ...

# research
@app.task(bind=True, max_retries=3)
def run_research(self, report_id, query_list, options): ...

# trend
@app.task(bind=True, max_retries=3)
def run_trend_scan(self, report_id, topic_keywords, options): ...

# competitor
@app.task(bind=True, max_retries=3)
def run_competitor_analysis(self, report_id, query, options): ...

# section
@app.task(bind=True, max_retries=5)
def generate_section(self, section_id, report_id, options): ...

# citation
@app.task(bind=True, max_retries=3)
def extract_citations(self, report_id, section_id, candidate_sources): ...

# embedding
@app.task(bind=True, max_retries=5)
def create_embeddings(self, report_id, chunk_ids): ...

# assemble
@app.task(bind=True, max_retries=3)
def assemble_report(self, report_id): ...

# export
@app.task(bind=True, max_retries=3)
def export_report(self, report_id, format): ...

```

---

## Implementation priorities & rollout suggestions

1. Implement Section Writer, Research, Embedding, and Export first — they form the critical path.
2. Add Outline & Assembler next.
3. Add Trend, Competitor, Citation workers iteratively.
4. Add robust DLQ, admin replay UI, and observability before opening to users.

---

If you want, I can:

- generate **worker skeleton code** (FastAPI + Celery + SQLAlchemy) for any worker you pick, ready to run; OR
- produce **OpenAPI / message contract definitions** for orchestrator ↔ worker payloads; OR
- produce **a visual Mermaid diagram** showing all workers with DB and queue flows (updated to reflect the LLD).

Which would you like next?