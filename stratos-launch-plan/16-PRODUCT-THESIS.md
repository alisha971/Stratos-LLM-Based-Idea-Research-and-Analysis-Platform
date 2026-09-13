# 16 — Product Thesis: The Reasoned Verdict

**Status:** Adopted August 2026. This doc defines *what Stratos is* and the product edge every
worker upgrade must serve. Read it before 02 (Target Architecture) changes, before writing any
prompt in `prompts/`, and before any copy/positioning work (doc 09).

---

## 1. Identity — one sentence

> **Stratos is a reasoning instrument: it turns a vague idea into a defensible decision by
> building the case for it, the case against it, and showing the weighing.**

Stratos is **not** an "AI validator" (a score without evidence), **not** a deep-research tool
(evidence without a judgment), and **not** a business-plan generator (which assumes the idea is
already good). It sits on the empty spot between the three: an interviewed, evidence-archived,
two-sided brief that ends in a verdict you can disagree with *at a specific step*.

The closest analogy is not another AI tool. It is a **legal brief** or an **intelligence
assessment**: thesis → evidence for → evidence against → stated unknowns → weighed judgment.

## 2. Why this and not "verdict + citations"

Competitive reality (researched Aug 2026):

- "Verdict + linked sources" is already shipped by Preuve AI ($29 scorecard, 50–60 live
  sources) and claimed by DimeADozen ($59–129 long reports; citation quality publicly disputed).
- Pure validators (ValidatorAI, IdeaProof, VenturusAI, …) are training-data opinions with no
  retrieval — reviewers call them "fast, free, and unaccountable."
- Deep-research incumbents (Perplexity/ChatGPT/Gemini) produce cited reports with measured
  citation-failure rates of 37%+ and **no judgment**.

Every one of these — including the good ones — is a **confirmation machine**: it settles on a
conclusion, then presents evidence as decoration for it. None of them (a) researches the counter-
case on purpose, (b) shows the weighing, or (c) admits what it could not find out. Those three
gaps are the product.

## 3. The three commitments

Everything below is an addition to the existing pipeline. **Nothing is rebuilt.** The pipeline is
already shaped like an argument (clarify → outline → gather evidence → write → assemble); these
commitments make the argument structure explicit instead of flattening it into report prose.

### C1. Every piece of evidence carries a stance

Each evidence item extracted by the research/trend/competitor workers is classified against the
session thesis as one of:

| Stance | Meaning |
|---|---|
| `supports` | Makes the idea more viable if true |
| `contradicts` | Makes the idea less viable if true |
| `complicates` | True but cuts both ways / conditions the answer |

The research phase runs a **dedicated counter-evidence pass**: after the normal queries, a
"steelman the failure case" query set explicitly hunts for reasons the idea fails (existing
failed competitors, saturation signals, regulatory walls, negative demand signals).

The report renders key questions as **for / against, side by side**, with the archived quoted
snippet next to each stance label — so a mislabeled stance is *visible*, never silently
misleading.

### C2. The verdict shows its weighing

The report ends in a verdict (**Go / Pivot / No-Go** per key dimension), written like a judge's
opinion, not a black-box number:

- "The demand evidence outweighs the competition risk **because** X."
- "This conclusion **flips if** Y."

Rules: no naked scores; every verdict line must reference evidence items by citation; every
dimension names the strongest surviving counter-argument. A reader must be able to reject the
verdict at a specific step, not just accept or ignore it.

### C3. The report states its unknowns

A first-class **Unknowns** section lists: questions the clarification surfaced that the web
could not answer, queries that came back thin (already observable in worker telemetry), and
sources that were inaccessible. Empty-handed honesty is a feature; confident filler is a defect.

## 4. Implementation mapping (deltas only)

| Area | File(s) | Delta |
|---|---|---|
| Evidence schema | `app/services/astra_evidence_repository.py`, Astra `evidence` docs | Add `stance` (`supports\|contradicts\|complicates`) + `stance_rationale` (one line) per evidence item |
| Research worker | `app/workers/research_worker.py` (W3) | Add counter-evidence query pass after the standard pass; tag all extracted evidence with stance at extraction time (one prompt call, batched) |
| Research prompt | `prompts/P3-RESEARCH.md`, `app/llm/prompts.py` | Extraction prompt gains stance classification + rationale in its output schema; new "steelman the failure case" query-generation prompt |
| Section writer | `app/workers/section_worker.py` (W6), `prompts/P6-SECTION-WRITER.md` | Brief format: each key question renders strongest-for vs strongest-against with quoted snippets; writer receives evidence grouped by stance |
| Assembler | `app/workers/assembler_worker.py` (W8), `prompts/P7-DEEPDIVE-AND-ASSEMBLER.md` | New verdict step: weighed judgment per dimension (C2 rules) + Unknowns section fed from thin-query telemetry |
| Export | export worker (W9), templates | Verdict page first, brief sections, Unknowns section, per-claim archived snippets in citations |
| Contract | `05-INTEGRATION-CONTRACT.md` | Report payload gains stance fields + verdict + unknowns blocks — **contract doc updates in the same PR** (see `stratos-contract-guard` skill) |
| Frontend | report view | Render stance-paired evidence and the verdict weighing; SSE already streams the process (keep it visible — the glass-box run is part of the identity) |

Cost note: the counter-evidence pass roughly doubles research-phase queries per key question.
Acceptable; prefer fewer, better-sourced key questions over more shallow ones (quality over
quantity is a product rule, not just a style preference).

## 5. Non-goals

- **No 0–100 viability score.** That is Preuve's product and it is exactly the black-box move
  this thesis rejects.
- **No 150-page reports.** Bulk is the DimeADozen failure mode. A tight brief beats a long opinion.
- **No pretending to certainty.** If the evidence is thin, the report says so — that is C3.
- **No Reddit-dependence.** Demand-signal mining is category fuel, but GummySearch died on
  Reddit API licensing. Treat community sources as garnish; lean on stable-access sources
  (SERP, arXiv, GDELT, Google News, public filings).

## 6. Messaging (for doc 09 and any landing page)

The strawman angle, not the "real data" angle (Preuve owns that copy):

> Other tools judge a two-sentence version of your idea. Stratos interviews you, researches the
> real market **for and against** while you watch, and hands you a verdict with archived
> evidence behind every claim — and an honest list of what it couldn't find out.
