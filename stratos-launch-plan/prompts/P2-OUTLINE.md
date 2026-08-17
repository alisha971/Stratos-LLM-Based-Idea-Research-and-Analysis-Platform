# P2 — Outline Worker Prompt

Implements plan task W2-O3 (template-constrained outline with scope notes).

---

## `OUTLINE_SELECTION_PROMPT`

**Called:** once per report, after consent, with the template chosen by category (W2-O2). Temperature `0.2`. JSON mode.

```text
You are planning the table of contents for a market research report. You must work WITHIN the given template — you choose which optional sections to include and write a scope note for every section, but you may not invent sections outside the template.

CLARIFIED IDEA SUMMARY:
<data>
{{CLARIFIED_SUMMARY}}
</data>

TEMPLATE — REQUIRED SECTIONS (always included, in this order):
{{REQUIRED_SECTIONS_JSON}}

TEMPLATE — OPTIONAL SECTIONS (choose 2 to 4; each entry shows its "include when" criterion):
{{OPTIONAL_SECTIONS_JSON}}

Your tasks:
1. For EVERY required section, write a "scope_note": 15–25 words describing what this section should cover FOR THIS SPECIFIC IDEA. Be concrete — name the actual industry, customer, or geography from the summary. A scope note that could apply to any idea is a failure.
2. Select 2–4 optional sections whose "include when" criterion matches this idea. For each, give a one-sentence "reason" and a scope_note (same rules).
3. Do not rename sections. Do not add sections. Do not reorder required sections.

Example of a GOOD scope_note (idea: subscription dog-food service in the UK):
"Size the UK premium pet food market, subscription share, and average spend per dog household."

Example of a BAD scope_note:
"Analyze the market size and growth trends." (could be any idea — too generic)

Return ONLY this JSON:
{
  "required": [{"title": "<exact template title>", "scope_note": "..."}],
  "optional": [{"title": "<exact template title>", "reason": "...", "scope_note": "..."}]
}
```

**Output schema:** `required` covers every template-required title exactly once with a non-empty scope_note; `optional` has 2–4 entries whose titles exist in the optional template list.

**Post-parse validation (code, per W2-O3):**
1. Every required title present, no extras, no renames (compare against the template exactly).
2. Optional entries ⊆ template optional titles; count in [2,4] (accept 1 with a warning rather than failing).
3. Every scope_note 8–40 words (looser than the prompt asks — don't fail on word-count pedantry).
4. Generic-note check (cheap heuristic): if a scope_note contains none of the top-10 keywords from the clarified summary, log `generic_scope_note` — don't fail, but track it (it predicts weak sections).

**On failure (after 1 retry):** fall back to required sections only, each with scope_note = first sentence of the clarified summary + "as it relates to " + section title. Emit `outline_ready` regardless — never fail the pipeline over an outline (W2-O3 rule).
