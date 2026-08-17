# P4 — Trend Worker Prompts

Implements plan tasks W4-T2 (keyword picking), W4-T3 (clustering), W4-T5 (sentiment).

---

## 1. `TREND_KEYWORDS_PROMPT` (task T2 — for Google Trends momentum)

**Called:** once per report. Temperature `0.0`.

```text
Pick the 3 best Google Trends search keywords to measure public interest in this business idea's space.

CLARIFIED IDEA SUMMARY:
<data>
{{CLARIFIED_SUMMARY}}
</data>

Rules:
1. Keywords must be terms REAL PEOPLE actually type into Google — category names, not startup jargon. ("meal kit delivery" yes; "D2C food-tech platform" no.)
2. 1–4 words each.
3. Keyword 1 = the core category. Keyword 2 = the problem or use-case phrasing. Keyword 3 = the nearest established competitor category or product type.
4. No brand names of the user's own idea (it doesn't exist yet).

Return ONLY: {"keywords": ["...", "...", "..."]}
```

**On failure:** use the 2 most frequent non-stopword bigrams from the clarified summary.

---

## 2. `TREND_CLUSTERING_PROMPT` (task T3 — topic grouping)

**Called:** once, over collected item titles (cap 60). Temperature `0.2`. (Replaced by embedding clustering when W7 exists.)

```text
Group these trend item titles into topics. Titles about the same underlying story or theme belong together.

TITLES (numbered):
<data>
{{NUMBERED_TITLES}}
</data>

Rules:
1. Create at most 8 topics. Fewer is better if the items genuinely group.
2. Topic names: 2–5 plain words a business reader understands ("AI coding assistants", "EU regulation pressure") — never vague ("various news", "other").
3. Every title index appears in exactly one topic. If a title fits nothing, put it in a topic named "unclustered".
4. Base grouping only on the titles given. Do not invent topics with no members.

Return ONLY: {"topics": {"<topic name>": [1, 4, 7], "<topic name>": [2, 3]}}
```

**Post-parse validation:** ≤9 keys (8 + unclustered); indices valid and used exactly once (missing indices → append to "unclustered"; duplicated indices → keep first occurrence).
**On failure:** one cluster per source type (fallback grouping: "From Hacker News", "From news", …) — the report copy degrades gracefully.

---

## 3. `TREND_SENTIMENT_PROMPT` (task T5 — batched sentiment)

**Called:** once over the top-25 scored items. Temperature `0.0`.

```text
Tag the sentiment of each trend item from a market-opportunity perspective.

ITEMS (numbered, title + snippet):
<data>
{{NUMBERED_ITEMS}}
</data>

Tags:
- positive: growth, adoption, funding, success signals
- neutral: factual/technical developments with no clear direction
- negative: decline, failures, shutdowns, waning interest
- concern: regulation, lawsuits, backlash, safety issues (things a founder must watch)

Return ONLY: {"sentiments": {"1": "positive", "2": "concern"}}
```

**Post-parse validation:** values ∈ the 4 tags; missing indices default to "neutral".
**On failure:** all items tagged "neutral"; the report simply omits the sentiment mix line.
