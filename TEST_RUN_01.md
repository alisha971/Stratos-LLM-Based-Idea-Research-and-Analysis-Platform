# Stratos Backend — Test Run 01

**Date:** 2026-05-07  
**Environment:** Local (Windows 10)  
**Session ID tested:** `e35c46a6-a60a-4a0d-93b5-edeec4ea95d1`  
**Report ID:** `cf2e37da-8b12-4d6e-8d4a-7cb5dfdc1f13`

---

## Infrastructure Status

| Component | Status |
| --- | --- |
| FastAPI (Uvicorn) | Running on `http://127.0.0.1:8000` |
| Redis | Running (`localhost:6379`) |
| PostgreSQL | Running (`localhost:5432/stratos`) |
| Celery Worker | Connected and ready |
| Groq API | Reachable (HTTP 200) |
| SerpAPI | Reachable (HTTP 200) |
| Astra DB | Keys present / write path stubbed |

---

## Input Given

### API call
```
POST /orchestrate/orchestrate/start-session
  ?user_id=test-user-123
  &idea_description=something for freelancers
```

### Clarification chat follow-up
```
POST /orchestrate/orchestrate/clarification/chat
  ?session_id=e35c46a6-...
  &message=<detailed idea description below>
```

### Idea description (full, sent in clarification turn)

> Project Domain: Sales Technology / AI Automation (Lead Generation).  
> Target Persona: Independent freelancers, niche agencies, and solo consultants looking for high-ticket clients.  
> Core Problem: High competition and low margins on traditional job boards (Upwork, Fiverr) where "first-mover advantage" is lost the moment a public listing is created.  
> Current Workaround: Manually scrolling through Reddit, X, and LinkedIn groups for hours; or relying on generic, delayed email newsletters that aggregate jobs everyone else has already seen.  
> Proposed Solution: A lightweight Python-based background service that uses APIs (Reddit/X) to monitor keywords and an LLM to score the "hiring intent" of social posts, delivering instant notifications via a Telegram/Discord bot.  
> Differentiation: Unlike standard job scrapers, this uses Natural Language Understanding (NLU) to distinguish between someone just complaining about a bug and someone actively looking to hire a professional to fix it.

---

## Worker Outputs

### 1. Clarification Worker

**Tasks received and succeeded:** 3 tasks

| Task | Duration | Status |
| --- | --- | --- |
| Turn 1 (initial idea) | ~7.6s | Succeeded |
| Turn 2 (follow-up) | ~1.3s | Succeeded |
| Turn 3 (final turn) | ~2.6s | Succeeded |

**Final clarification schema produced:**

```json
{
  "project_domain": "freelancing",
  "target_persona": "Independent freelancers, niche agencies, and solo consultants looking for high-ticket clients",
  "core_problem": "High competition and low margins on traditional job boards (Upwork, Fiverr) where first-mover advantage is lost the moment a public listing is created",
  "current_workaround": "Manually scrolling through Reddit, X, and LinkedIn groups for hours",
  "proposed_solution": "Lightweight Python service using Reddit/X APIs + LLM to score hiring intent, delivering notifications via Telegram/Discord bot",
  "differentiation": "Uses NLU to distinguish between complaints and active hiring intent"
}
```

**Confidence score:** `1.0`  
**Remaining knowledge gaps:**
- `cost_of_service`
- `scalability`
- `user_acquisition_strategy`

**Research directives generated:**
1. Investigate feasibility of cloud-based API for keyword monitoring
2. Explore integrating multiple social media platforms beyond Reddit/X
3. Develop user acquisition strategy for proposed solution

**SSE events emitted:**
- `session_created`
- `clarification_started`
- `clarification_update` (low confidence turn: `0.17`)
- `clarification_update` (high confidence turn: `1.0`)
- `clarification_ready`
- `clarification_consent_requested`

**Consent call:**
```
POST /orchestrate/orchestrate/clarification/accept-consent
  ?session_id=e35c46a6-...
```

**SSE after consent:**
- `clarification_completed`

---

### 2. Outline Worker

**Task received and succeeded:** 1 task  
**Duration:** ~0.64s

**Sections generated:**

| Order | Title |
| --- | --- |
| 1 | Problem Context & Validation |
| 2 | Target Users & Personas |
| 3 | Existing Solutions |
| 4 | Competitor Landscape |
| 5 | Market & Industry Trends |
| 6 | Opportunities & Gaps |
| 7 | Risks & Open Questions |
| 8 | Technical Feasibility |

**SSE events emitted:**
- `outline_ready`
- `outline_accepted`

**Note:** `section_id` values in the outline payload are `null`. Sections are not yet persisted to the `sections` table before being passed downstream.

---

### 3. Research Worker

**Task received and succeeded:** 1 task  
**Duration:** ~82s

**LLM query generation:**
- Groq call returned `200 OK`
- 5 queries generated:
  1. Freelancing platforms with high-ticket client opportunities
  2. Natural Language Understanding job scraping tools
  3. Cloud-based API keyword monitoring services
  4. Social media job board platforms beyond Upwork and Fiverr
  5. Telegram and Discord bot integration for job notifications

**SERP results:**
- Each query returned ~19 results
- Total SERP entries: ~95

**Scraping:**
- 7 URLs returned `403` or `400` (anti-bot blocks)
- Successful scrapes proceeded and evidence saved

**Postgres persistence:**
- `sources` table: populated
- `source_evidence` table: **213 snippet rows saved**

**Astra persistence:**
- `save_to_astra()` is a stub → **nothing written to Astra**

**SSE events emitted:**
- `research_started`
- `searching_sources`
- `research_done`

---

## Evidence Quality Analysis

### Quantity
- 213 snippets stored across sources

### Relevance

| Category | Assessment |
| --- | --- |
| Upwork/Fiverr alternatives | ✅ Relevant |
| High-ticket freelancer guidance | ✅ Relevant |
| Telegram/Discord notification setup | ✅ Relevant |
| LangChain/NLP job scraping projects | ✅ Relevant |
| Generic SEO/API monitoring tools | ⚠️ Tangential |
| Crypto/trading bots | ❌ Off-topic |
| Dark web monitoring | ❌ Off-topic |
| Cybersecurity articles | ❌ Off-topic |
| Login walls, browser checks, boilerplate text | ❌ Noise |

### Root cause of noise
- Queries are too broad in scope (`cloud-based API keyword monitoring`)
- SERP returns news + web + patents for each query (3× volume per query)
- Evidence filtering only checks snippet length (`>=40 chars`) and bad prefix list
- No semantic relevance check against the clarified schema before storing

---

## SSE Event Flow Summary

```
session_created
clarification_started
clarification_update          ← confidence 0.17, asks follow-up
clarification_update          ← confidence 1.0, ready
clarification_ready
clarification_consent_requested
[user calls accept-consent]
clarification_completed
outline_ready
outline_accepted
research_started
searching_sources
research_done
```

---

## Issues Found

| # | Issue | Severity | Component |
| --- | --- | --- | --- |
| 1 | `section_id` is `null` in outline payload — sections not saved to DB before research starts | High | Outline Worker |
| 2 | `save_to_astra()` is a stub — no evidence written to Astra | High | Research Worker |
| 3 | Evidence quality is noisy — off-topic snippets stored (crypto, dark web, SEO tools) | High | Research Worker |
| 4 | No semantic relevance scoring before evidence is saved | High | Research Worker |
| 5 | Double URL prefix in API calls (`/orchestrate/orchestrate/...`) | Medium | API router config |
| 6 | Outline sections not linked to report before research fan-out | Medium | Orchestrator |
| 7 | Encoding artifacts in stored snippets (`ΓÇÖ`, `╨ò`, etc.) | Low | Research / text cleaner |
| 8 | `section_id` is null in SSE payload so frontend/downstream cannot link sections | Medium | Outline Worker |

---

## Improvement Plan

### Critical (must fix before section writing works)

**1. Save outline sections to DB and populate `section_id` in payload**
- Outline worker must persist sections to `sections` table before emitting `outline_ready`
- Fan-out to section writer workers requires valid `section_id`
- Currently sections are created in-memory only

**2. Implement `save_to_astra()`**
- Write scraped full text to Astra `evidence` collection
- Section writer worker reads from Astra — without this, RAG will have nothing to retrieve
- Implement using `astrapy` client with `report_id` + `source_id` + `raw_text` + `snippets`

**3. Add relevance filtering before evidence persistence**
- After scraping, score each snippet against the clarified schema using LLM or keyword match
- Only store snippets with relevance score above threshold
- Reduces noise from 213 → ~50-80 high-signal snippets

### Important (quality improvement)

**4. Sharpen SERP query generation**
- Queries like `cloud-based API keyword monitoring` are too generic and pull off-topic results
- Prompt should force queries to include domain-specific context (e.g., `freelancing`, `hire intent`, `Reddit API`)
- Consider adding explicit negative keywords to prompt

**5. Reduce SERP result volume per query**
- Currently each query fetches web + news + patents (~19 results each)
- For MVP, consider fetching web-only or reducing `limit` to 3 per type
- Reduces noise and scraping time

**6. Improve snippet quality filtering**
- Current filter: length >= 40 and no bad prefix
- Add: filter out known boilerplate patterns (`sign in`, `checking your browser`, `JavaScript is disabled`, `free trial`, `no credit card`)
- Add: filter out very short high-frequency phrases

### Minor (polish)

**7. Fix double router prefix `/orchestrate/orchestrate/...`**
- In `app/api/orchestrator.py`, router is declared with `prefix="/orchestrate"` and registered on app also with `prefix="/orchestrate"`
- Fix: remove one prefix

**8. Fix encoding artifacts in stored snippets**
- Some scraped text is stored with encoding artifacts (`ΓÇÖ` = `'`, `╨ò` = Cyrillic chars)
- Add encoding normalization in `text_cleaner.py` after HTML cleaning (decode via `ftfy` or `unidecode`)
