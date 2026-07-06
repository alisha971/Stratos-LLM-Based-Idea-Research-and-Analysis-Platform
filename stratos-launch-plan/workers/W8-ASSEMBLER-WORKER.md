# W8 — Assembler Worker: Upgrade Plan

## 1. What it does today (plain language)

After all sections are written, this worker (`app/workers/assembler_worker.py`) staples them together: reads sections/chunks/citations from Postgres, writes one JSON file to `exports/{report_id}.json`, flips the report status, and emits `report_assembled`. No editing, no summary, no consistency checking — a stapler, not an editor. It also never saves the final text to the database (only to a local file), which the main plan flags as a gap.

## 2. Who it competes with (the quality bar)

The editorial layer of Deep Research products and human analyst workflows. What readers notice in a finished report: an **executive summary** up front (most-read part of any report — often the only part), smooth transitions, no contradictions between sections ("$4B market" in one section, "$9B" in another), a references list, and consistent terminology. That's the gap between "AI output" and "a report I'd forward to my board".

## 3. Feature plan (do in order)

### A1 — Persist final text to the database

- Add `final_text` (or a `report_documents` table with `markdown` column via Alembic) and write the assembled markdown there as well as to the JSON file. `GET /reports/{id}` should not depend on a file on one machine's disk. Do this first — it's a production correctness fix, not a feature.

### A2 — Executive summary generation

- One LLM call: input = each section's first 2 paragraphs + the trend momentum line (W4-T2) + the competitor whitespace paragraph (W5-K4); output = 150–220 words, structured: one sentence on the opportunity, 3–4 bullet key findings (each must trace to a section — include section refs), one sentence on the primary risk. Insert as section 0 titled "Executive Summary".
- Grounding rule in the prompt: "Use only statements present in the sections. No new facts, no new numbers." Then run the W6-S3 numeric guard over the summary against the sections' text (a summary hallucination is maximally embarrassing — it's the first thing read).

### A3 — Cross-section consistency check

- Deterministic pass first: extract all numbers+units per section (reuse the W6-S3 extractor). Where two sections state different values for what regexes suggest is the same quantity (same unit + overlapping keyword window, e.g. "market size"), flag it.
- One LLM adjudication call per flag (max 5): "Sections A and B disagree (X vs Y). Given their citations, which is better supported? Rewrite the weaker sentence to align or to attribute both ('estimates range from X to Y')." Apply the rewrite to the weaker section's chunk.

### A4 — Transitions + terminology smoothing

- One LLM call per section boundary is too expensive; instead one batched call: input = last paragraph of each section + first paragraph of the next; output = an optional single bridging sentence per boundary (or "NONE"). Append accepted bridges to the earlier section's final chunk.
- Terminology: build a frequency map of the 5 most-used entity names (company/product names, the idea's category term); if variants appear ("e-commerce" vs "ecommerce", "Acme Inc" vs "Acme"), normalize to the most frequent form via string replace (deterministic, no LLM).

### A5 — References section

- Generate a final "References" section: deduped citations across all sections, numbered, formatted `[$n] Title — domain (URL), accessed {date}`, ordered by first appearance. Persist as a real section so both the UI and the PDF (W9) get it for free. Map inline `CIT-XXX` markers to the reference numbers during assembly.

### A6 — Quality gate + report score

- Compute and store on the report: mean section `audit_score` (W6-S2), evidence count, tier-A/B source share, consistency flags resolved. If mean audit_score < 0.85 → emit a `quality_warning` event (surfaced subtly in the UI as "sources were limited for parts of this report") rather than blocking. Honest signaling beats silent shipping.

### A7 — Standalone product mode (optional)

`POST /v1/assemble` with `{sections: [{title, markdown, citations}]}` → summary + consistency report + references + merged document. A "document finishing" API for other AI-writing products. Lowest standalone priority of all workers.

## 4. Testing checklist (run all before production)

1. **A1 test:** after a run, `GET /reports/{id}` serves the full report from the DB with the JSON file deleted from disk (simulate a fresh container).
2. **Summary grounding (release blocker):** fixture report whose sections never state a market-size figure → executive summary must not contain one. Also: every bullet's content must appear in some section (LLM-judge assertion). 3 runs.
3. **Consistency unit test:** two fixture sections stating "$4B (2025)" and "$9B (2025)" for the same market → flag raised, adjudication invoked, final text contains either one aligned figure or an explicit range. A false-positive check too: "$4B market" and "$9B funding total" must NOT be flagged (different quantity kinds).
4. **References test:** citations used in 3 sections, one URL shared by two sections → references list has it once; every inline marker resolves to an existing reference number; zero orphan markers (deterministic assertion).
5. **Terminology test:** fixture with "Acme Inc"/"Acme" mixed → output uses one form everywhere except inside direct quotes/URLs.
6. **Order/latency/cost:** assembler completes ≤ 60 s p50 and ≤ 8 LLM calls for an 8-section report (log both).
7. **Fail-soft:** each LLM sub-step mocked to fail → assembly still completes with that enhancement skipped and logged; `report_assembled` always fires after `sections_done`.
8. **Regression:** pipeline smoke passes; export worker (W9) renders the new Executive Summary and References sections.
