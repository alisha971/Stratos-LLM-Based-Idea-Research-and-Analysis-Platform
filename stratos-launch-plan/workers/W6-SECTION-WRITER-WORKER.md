# W6 — Section Writer Worker: Upgrade Plan

## 1. What it does today (plain language)

This is the "author" (`app/workers/section_worker.py` + `app/services/section_writer_service.py`). For each outline section it gathers the ranked evidence bundle (from Astra, Postgres fallback), builds a prompt with numbered citations (`CIT-001`…), asks the LLM to write the section, validates the draft (title matches, citations exist, chunks sequenced), retries once on failure, saves chunks + citations, and streams `section_chunk` events. It is one of the strongest workers — the validation loop already exists.

**Weaknesses:** validation checks citation **format**, not citation **truth** (the model can cite CIT-003 for a claim CIT-003 doesn't support — the classic subtle hallucination); numbers can be invented; style/length varies section to section; all sections use one generic prompt regardless of what the section is (a market-size section and a risks section need different treatment); "streamed" chunks are actually written in bulk.

## 2. Who it competes with (the quality bar)

The writing stage of **OpenAI/Perplexity/Gemini Deep Research** and grounded-writing engines. Their bar: every factual sentence is attributable; numbers trace to sources; consistent professional register; and when evidence is thin the text **says so** rather than fabricating. Trust is the entire product — one caught hallucination costs a customer.

## 3. Feature plan (do in order)

### S1 — Per-section-type prompts

- **File:** `app/llm/prompts.py`. Replace the single section prompt with a base prompt + per-type addendum keyed by section title/template role (from W2's templates): market-size sections must lead with numbers + explicit years and mark estimates as estimates; competitor sections follow the K4 synthesis; risk sections must present both likelihood and mitigations; trends sections lead with momentum (W4-T2). 6–8 addenda, each 3–5 sentences.
- Feed the section's `scope_note` (W2-O3) into the prompt. Set target length per type (market size 250–350 words; executive-adjacent sections shorter).

### S2 — Claim-level citation audit (the flagship accuracy feature)

- After a draft passes the existing format validation, run an **auditor LLM call**: input = the draft split into sentences + the actual text of each cited evidence snippet; output JSON per cited sentence: `{sentence_idx, marker, verdict: supported|partial|unsupported}`.
- Handling: `unsupported` sentences → one repair call ("rewrite these sentences using only the provided evidence, or delete the claim"); if still unsupported → **delete the sentence** (a shorter honest section beats a longer lying one). `partial` → soften wording ("suggests", "reportedly").
- Log an `audit_score` (supported ÷ total cited) per section; store on the `Section` row. This number is your marketing claim ("every report ships with ≥ 95% verified-citation rate").

### S3 — Numeric guard

- Regex-extract every number+unit ($X B, X%, X million users, years) from the draft; each must appear (normalized: "4.2 billion" ≈ "$4.2B") in the cited snippet text. Unmatched numbers get the S2 repair treatment. Cheap, deterministic, catches the most embarrassing class of hallucination.

### S4 — Thin-evidence honesty mode

- If a section's bundle has < 3 evidence items or mean credibility (W3-R4) < 0.4: switch to a constrained prompt that writes a shorter section explicitly framed as directional ("Public data on this niche is limited; the signals available suggest…"). Never let the model compensate for missing evidence with confidence.

### S5 — True token streaming

- Groq supports streaming. Change the client call to `stream=True`; buffer into ~400-char chunks and publish `section_chunk` as they arrive (persist chunks at natural paragraph boundaries as today). Perceived speed doubles with zero real speedup — the UI shows words appearing live.

### S6 — Style consistency pass

- Add a fixed style card to every prompt (person, tense, no first person, no marketing adjectives, US spelling, "the company" not "our company"). Deterministic post-check: forbidden-phrase list ("game-changer", "in today's fast-paced world", "delve"…) triggers one rewrite of offending sentences.

### S7 — Standalone product mode (optional)

`POST /v1/write-grounded` with `{brief, evidence: [{id, text, url}], style}` → `{draft, citations, audit_report}`. A "grounded writing API" — sellable to any content/report tool that needs citations. The audit report (S2) is the differentiator no cheap competitor ships.

## 4. Testing checklist (run all before production)

1. **Audit unit tests** (`tests/` — extend the existing suite, the only one in the repo): synthetic cases — (a) sentence supported by its snippet → `supported`; (b) sentence citing a snippet about something else → `unsupported` → repaired or deleted in final text (assert the fabricated claim string is absent); (c) audit LLM call itself failing → section still completes, `audit_score` null, warning logged.
2. **Numeric guard unit tests:** draft containing "$7.3B" with no 7.3 anywhere in evidence → flagged; "≈$7 billion" vs snippet "roughly $7bn" → passes normalization.
3. **Thin-evidence test:** run a section with 1 evidence item → output contains an explicit limited-data disclaimer and is < 200 words.
4. **Streaming test:** during a live run, assert ≥ 3 `section_chunk` events arrive for a section BEFORE its `section_done` (timestamps), and concatenated chunk text equals the persisted section text.
5. **Adversarial eval (release blocker):** craft 5 evidence bundles that DON'T contain the answer to an obvious question (e.g. market-size section with evidence that never states a market size). Generated sections must not state a specific market size figure. Any fabricated figure = blocker. Paste outputs in the PR.
6. **Quality eval (manual):** 3 full reports; a human (or judge LLM with the rubric) scores each section 1–5 on accuracy-vs-sources, usefulness, and tone; target mean ≥ 4.0, no section < 3. Record `audit_score`s — target ≥ 0.95 mean.
7. **Cost/latency:** audit adds ~1 LLM call/section — total per-report LLM calls must stay ≤ 45 (log the count); section phase p50 ≤ 4 min for 8 sections.
8. **Regression:** pipeline smoke passes; existing 5 validation tests still green.
