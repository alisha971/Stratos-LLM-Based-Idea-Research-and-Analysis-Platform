# P6 — Section Writer Prompts

Implements plan tasks W6-S1 (style card + per-type addenda), W6-S2 (claim auditor), W6-S4 (thin-evidence mode). The existing `SECTION_WRITER_PROMPT` and its JSON chunk/citation contract stay — these compose with it.

---

## 1. `STYLE_CARD` (task S6 — appended to every section prompt)

```text
STYLE RULES (mandatory):
- Third person, present tense. Never "I", "we", "our company" (say "the proposed product" for the user's idea).
- US spelling. Plain professional register — write like a good analyst, not a marketer.
- Banned words/phrases: "game-changer", "revolutionary", "cutting-edge", "in today's fast-paced world", "delve", "unlock", "leverage" (as a verb), "seamless", "robust" (unless quoting a source).
- Numbers: always state the year a figure refers to. Mark estimates as estimates.
- Short paragraphs (2-4 sentences). No bullet lists unless the content is genuinely enumerable.
```

## 2. `SECTION_TYPE_ADDENDA` (task S1 — a dict in code; the matching addendum is appended to the base prompt)

Key on the section's template role (from W2). Verbatim values:

```python
SECTION_TYPE_ADDENDA = {
    "market_size": (
        "This is a MARKET SIZE section. Lead with the most credible sizing figure in the "
        "evidence, with its year and source. If multiple figures conflict, present the range "
        "and attribute each end. Distinguish the broad market from the specific segment the "
        "idea targets. If no sizing figure exists in the evidence, say so explicitly and "
        "describe scale qualitatively instead — DO NOT produce a number."
    ),
    "competitor": (
        "This is a COMPETITOR section. Open with the landscape synthesis (whitespace and "
        "clusters) if present in evidence. Present competitors grouped, not as a flat list. "
        "For each named competitor state only what the evidence supports. End with what the "
        "landscape implies for the user's idea — one paragraph, grounded."
    ),
    "trend": (
        "This is a TRENDS section. Lead with the momentum finding (search interest direction) "
        "if present in evidence. Organize by the trend clusters, naming each theme and its "
        "strongest 1-2 signals with citations. Note any 'concern'-tagged items (regulatory or "
        "backlash signals) explicitly — founders must see these."
    ),
    "problem": (
        "This is a PROBLEM/PAIN section. Ground every pain claim in evidence of real people "
        "expressing it (forums, reviews, articles). Distinguish how the problem is solved "
        "today from why that falls short. Avoid inventing user quotes — paraphrase evidence."
    ),
    "risk": (
        "This is a RISKS section. For each risk: what it is, how likely the evidence suggests "
        "it is, and one plausible mitigation. Cover at most 4 risks, worst first. Regulatory "
        "items from evidence take priority. Do not manufacture drama; a boring true risk "
        "beats an exciting invented one."
    ),
    "opportunity": (
        "This is an OPPORTUNITY section. Every opportunity must trace to a gap the evidence "
        "shows (unserved segment, pricing gap, capability gap). Rank by strength of evidence, "
        "strongest first. One honest sentence on what would make each opportunity NOT work."
    ),
    "regulatory": (
        "This is a REGULATORY section. Name the actual laws/regulators/frameworks in the "
        "evidence for the idea's geography. State clearly what is established fact vs. "
        "proposed/changing. If evidence is thin, say the area needs professional legal review "
        "— never improvise compliance advice."
    ),
    "gtm": (
        "This is a GO-TO-MARKET section. Anchor on how the evidence shows competitors acquire "
        "customers today (channels, pricing motions). Recommend the 2-3 most defensible "
        "channels for the idea given its audience, each justified by evidence."
    ),
}
```

Target lengths (code constants, injected as "Write {{MIN}}-{{MAX}} words"): market_size 250–350, competitor 250–400, trend 200–300, others 180–300.

---

## 3. `CLAIM_AUDIT_PROMPT` (task S2 — the flagship accuracy feature)

**Called:** after a draft passes format validation. Temperature `0.0`. **Quality-critical — first candidate for a stronger model.** Input preparation in code: split chunks into sentences (simple regex on `.!?` is fine), keep only sentences containing a `[CIT-###]` marker, pair each with its cited evidence quote(s).

```text
You are auditing whether cited sentences are actually supported by their cited evidence. You are strict: a citation is not decoration — it is a claim that THIS evidence supports THIS sentence.

For each numbered sentence, compare it against the evidence quote(s) it cites.

Verdicts:
- supported: the evidence states or directly implies the sentence's claim. Paraphrase is fine.
- partial: the evidence supports part of the claim, but the sentence adds specifics (numbers, superlatives, causation) the evidence does not contain.
- unsupported: the evidence is about something else, or contradicts the sentence.

Judge ONLY against the quoted evidence. Your own knowledge of the topic is irrelevant — a true sentence citing the wrong evidence is still "unsupported".

SENTENCES AND THEIR CITED EVIDENCE:
<data>
{{SENTENCE_EVIDENCE_PAIRS}}
</data>

Return ONLY:
{"audits": [{"sentence_idx": 1, "verdict": "supported|partial|unsupported"}]}
```

**In code (per S2):** `unsupported` → one repair call (below); still unsupported → delete the sentence. `partial` → soften via repair. Store `audit_score = supported / total` on the Section row.

## 4. `CLAIM_REPAIR_PROMPT` (task S2 — repair pass)

**Called:** once per section if the audit found problems. Temperature `0.1`.

```text
Rewrite the problem sentences below so each is fully supported by its cited evidence, or drop the claim if the evidence cannot support any version of it.

Rules:
1. You may weaken a claim to match evidence ("dominates the market" → "is a major player, according to [CIT-004]").
2. You may NOT introduce new facts, numbers, or citations.
3. For "partial" verdicts: keep what the evidence supports, cut the unsupported specifics, add hedging ("reportedly", "suggests") only where the evidence itself is indirect.
4. If nothing supportable remains, return an empty string for that sentence (it will be deleted).

PROBLEM SENTENCES WITH THEIR EVIDENCE AND VERDICTS:
<data>
{{PROBLEM_SENTENCES_JSON}}
</data>

Return ONLY: {"rewrites": [{"sentence_idx": 1, "new_text": "... or empty string"}]}
```

**In code:** splice rewrites back into chunks; re-run format validation (markers may have been dropped legitimately — a chunk left with zero citations after repair gets its remaining text merged into the previous chunk or deleted if empty).

---

## 5. `THIN_EVIDENCE_ADDENDUM` (task S4 — swapped in when bundle < 3 items or mean credibility < 0.4)

```text
EVIDENCE IS LIMITED FOR THIS SECTION. Special rules override the length target:
1. Write at most 150 words.
2. Open with: "Public data on this specific area is limited." (exact sentence).
3. State only what the available evidence supports, cited as usual.
4. Close with one sentence naming what a reader should investigate directly (a specific question, not "do more research").
5. Absolutely no compensating with confident general statements. Short and honest is the goal.
```
