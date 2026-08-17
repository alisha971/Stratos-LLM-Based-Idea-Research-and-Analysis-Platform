# P3 — Research Worker Prompts

Implements plan tasks W3-R3 (typed query planner) and W3-R6 (coverage self-check).

---

## 1. `RESEARCH_QUERY_PLANNER_PROMPT` (task R3)

**Called:** once at research start. Temperature `0.2`. Replaces the current free-form `RESEARCH_QUERY_PROMPT`.

```text
You are planning web searches for a market research report. Generate search queries for EXACTLY the slots below — this systematic coverage matters more than creativity.

CLARIFIED IDEA SUMMARY:
<data>
{{CLARIFIED_SUMMARY}}
</data>

CURRENT YEAR: {{YEAR}}
REGULATORY SECTION INCLUDED IN OUTLINE: {{HAS_REGULATORY_SECTION}}

Fill these slots (each query 3–10 words, ready to paste into Google):
- market_size_1: "<industry> market size <YEAR>" style — use the REAL industry name from the summary
- market_size_2: a TAM/forecast/growth-rate variant of the above
- competitors_1: find named competitors ("best <category> tools/companies <YEAR>" or "<category> competitors")
- competitors_2: an alternatives/comparison variant
- customer_pain_1: find real customer complaints/needs (forums, reviews, "problems with <current solution>")
- customer_pain_2: a different angle on the pain (job-to-be-done phrasing)
- pricing: how existing solutions price ("<category> pricing")
- regulation: ONLY if HAS_REGULATORY_SECTION is true, else empty string ("<industry> regulations <geography>")
- recent_news: newest developments ("<industry> news" — the news engine adds recency)

Disambiguation rule: if the idea's key term is ambiguous (e.g. "apple", "python", "swift"), append minus-operators to EVERY query to exclude the wrong meaning (e.g. "-iphone -mac").

Use the geography from the summary in queries where location changes the answer (market size, regulation, pricing).

Return ONLY:
{"queries": {"market_size_1": "...", "market_size_2": "...", "competitors_1": "...", "competitors_2": "...", "customer_pain_1": "...", "customer_pain_2": "...", "pricing": "...", "regulation": "", "recent_news": "..."}}
```

**Post-parse validation:** all 9 keys present; each non-empty value has 3–12 words; drop (don't fail on) individual bad slots; dedupe by normalized text before spending provider credits (R3 rule).
**On failure:** the existing deterministic fallback queries, prefixed with the idea's main noun phrase extracted by simple heuristics (first capitalized phrase or first 4 non-stopwords of the summary) — better than today's fully generic fallback.

---

## 2. `RESEARCH_COVERAGE_CHECK_PROMPT` (task R6)

**Called:** once, after evidence is saved, if query budget remains. Temperature `0.0`. This is the "reflect and re-search" step.

```text
You are auditing whether gathered research evidence is sufficient to write each section of a report. Judge coverage, not quality of writing.

REPORT SECTIONS AND WHAT EACH MUST COVER:
{{SECTIONS_WITH_SCOPE_NOTES_JSON}}

EVIDENCE GATHERED (titles + snippets only):
<data>
{{EVIDENCE_TITLES_AND_SNIPPETS}}
</data>

For each section, decide if the evidence contains material to write it. A section has a GAP if a reader could not answer its scope note from this evidence.

Common gap types: "no market size numbers", "no named competitors", "no pricing information", "nothing recent (all evidence is old)", "no <geography>-specific evidence".

Return the 0–3 WORST gaps only (empty list if coverage is adequate):
{"gaps": [{"section": "<exact section title>", "missing": "<gap in under 10 words>", "suggested_query": "<one search query, 3-10 words, that would fill it>"}]}
```

**Post-parse validation:** ≤3 gaps; each `section` matches a real section title (drop non-matching entries); each `suggested_query` 3–12 words.
**In code:** run at most the top gap's query (or up to 3 if budget allows), one round only — the loop is bounded by design, never recursive.
**On failure:** skip the re-search round entirely; proceed with existing evidence. This step is an enhancer, never a blocker.
