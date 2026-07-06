# SERP Integration

[Progress till now + metric 😋](SERP%20Integration/Progress%20till%20now%20+%20metric%20%F0%9F%98%8B%202f183f23b1658099bd7cfdb5a518ba15.md)

# SERP Integration – Implementation Plan & Rationale

## 1. Overview

This document summarizes the **design decisions, implementation plan, and rationale** behind integrating a Search Engine Results Page (SERP) provider into the research pipeline. The goal is to reliably discover high-quality external sources (web, news, patents) that can be used as evidence for downstream LLM-based report generation.

---

## 2. Why SERP Integration Is Needed

### Problem Statement

Directly scraping Google/Bing search result pages is:

- Fragile (HTML changes frequently)
- Legally risky
- Rate-limited and IP-blocked
- Difficult to scale

The research system needs:

- Structured search results
- Multiple verticals (web, news, patents)
- Stable APIs with predictable schemas
- Fault tolerance under partial failures

---

## 3. Why SerpAPI Was Chosen

### Key Reasons

1. **API-based Access**
    - Eliminates direct scraping of search engines
    - Returns structured JSON
2. **Multi-Vertical Support**
    - Google Web (`engine=google`)
    - Google News (`tbm=nws`)
    - Google Patents (`tbm=pts`)
3. **Reliability & Observability**
    - Clear error messages (e.g., empty results, quota issues)
    - Predictable response formats
4. **Fast Integration for MVP**
    - Python SDK available
    - Minimal setup
    - No browser automation required
5. **Decoupling Search from Scraping**
    - SERP provides *discovery*
    - Scraper handles *content extraction*

> For MVP, SerpAPI provided the best tradeoff between speed, reliability, and implementation complexity.
> 

---

## 4. High-Level Architecture

```
Clarified User Intent
        ↓
Query Generation (LLM)
        ↓
SERP Search (Parallel Queries)
        ↓
URL Deduplication
        ↓
Source Classification (web / news / patent)
        ↓
┌───────────────┬──────────────────┐
│ News Sources  │ Web Sources      │
│ (snippets)    │ (scraped HTML)   │
└───────────────┴──────────────────┘
        ↓
Postgres (metadata + snippets)
        ↓
AstraDB (raw cleaned content – future)

```

---

## 5. Implementation Plan

### Step 1: Query Generation

- Use LLM to expand clarified summary into 3–5 focused search queries
- Validate query length and structure
- Provide deterministic fallback queries on failure

**Why:**

- Improves recall
- Covers multiple angles of the same research topic

---

### Step 2: SERP Execution

For each query, execute the following SERP calls:

| Vertical | Purpose |
| --- | --- |
| Web | Blogs, docs, technical articles |
| News | Fresh, editorial, high-authority sources |
| Patents | Prior art, technical innovation |

Implementation details:

- Uses SerpAPI Google engine
- Enforces result limits per vertical
- Normalizes output to a common schema

---

### Step 3: Parallel Query Execution

- Queries are executed **in parallel** using worker-level concurrency
- Each query runs independent SERP calls

**Benefits:**

- Reduces overall latency
- Isolates failures per query
- Improves scalability

Measured impact:

- Sequential execution: ~45–55s
- Parallel execution: ~30–32s
- **~30–40% latency reduction**

---

### Step 4: URL Deduplication

- Deduplicate at two levels:
    - In-memory (per run)
    - Database-level (per report)

**Why:**

- Prevents redundant scraping
- Reduces cost and noise

---

### Step 5: Source Classification

Each SERP result is tagged as:

- `web`
- `news`
- `patent`

Stored directly in the `sources.type` column.

This enables:

- Selective scraping
- Different evidence handling strategies
- Future ranking and weighting

---

### Step 6: Evidence Handling Strategy

| Source Type | Handling |
| --- | --- |
| News | Use SERP-provided snippet directly |
| Web | Scrape HTML → clean → extract snippets |
| Patent | Store metadata only (MVP) |

**Design Choice:**

- Postgres stores only *lightweight evidence*
- Raw content is intended for AstraDB (vector store)

---

## 6. Error Handling & Known Limitations

### 403 Errors During Scraping

Observed on:

- Reddit
- Medium
- Upwork

**Root cause:**

- Bot protection
- Higher concurrency

**Current handling (MVP):**

- Gracefully skip
- Continue pipeline

**Future improvements:**

- Headless browsers
- Proxy rotation
- Domain allow/block lists

---

### Encoding Issues in Postgres

- Some scraped content contains emojis / Unicode
- MVP decision: store **only short snippets** in Postgres
- Full content will be stored in AstraDB

This is an intentional design tradeoff.

---

## 7. Why This Design Works for MVP

This implementation:

- Is production-aligned
- Is fault-tolerant
- Has clear separation of concerns
- Is easy to extend (ranking, scoring, re-fetching)

Most importantly:

> It works end-to-end and produces usable research evidence today.
> 

---

## 8. Future Enhancements (Post-MVP)

- Domain quality scoring
- Evidence relevance ranking
- Async scraping pools
- AstraDB ingestion
- Section-level citation mapping
- SERP provider abstraction (Bing, Brave, etc.)

---

## 9. Summary

The SERP integration forms the backbone of the research pipeline by providing reliable, structured discovery of external knowledge. SerpAPI was chosen to maximize development speed and reliability for MVP, while keeping the architecture flexible enough to support future search providers and deeper evidence processing.