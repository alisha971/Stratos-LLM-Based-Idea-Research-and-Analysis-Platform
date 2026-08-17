# Prompt Library — Index & Conventions

Verbatim, copy-paste-ready prompt templates for **every LLM call** the implementation plans introduce. This closes the biggest gap for smaller AI models implementing the worker plans: instead of authoring prompts from a description, paste these into `app/llm/prompts.py` (or a new `app/llm/prompts/` package) and wire them up.

## Files

| File | Covers | Used by plan |
|---|---|---|
| [P1-CLARIFICATION.md](P1-CLARIFICATION.md) | Coverage judge, category classifier, adaptive question generator, multi-answer schema merge | `../workers/W1-CLARIFICATION-WORKER.md` |
| [P2-OUTLINE.md](P2-OUTLINE.md) | Template-constrained outline selection with scope notes | `../workers/W2-OUTLINE-WORKER.md` |
| [P3-RESEARCH.md](P3-RESEARCH.md) | Typed query planner, coverage self-check | `../workers/W3-RESEARCH-WORKER.md` |
| [P4-TREND.md](P4-TREND.md) | Keyword picker, topic clustering, sentiment batch | `../workers/W4-TREND-WORKER.md` |
| [P5-COMPETITOR.md](P5-COMPETITOR.md) | Candidate discovery, SERP extraction, profiler, grounding self-check, landscape synthesis | `../workers/W5-COMPETITOR-WORKER.md` |
| [P6-SECTION-WRITER.md](P6-SECTION-WRITER.md) | Style card, per-section-type addenda, claim auditor, repair instructions, thin-evidence variant | `../workers/W6-SECTION-WRITER-WORKER.md` |
| [P7-DEEPDIVE-AND-ASSEMBLER.md](P7-DEEPDIVE-AND-ASSEMBLER.md) | Deep-dive Q&A; executive summary, consistency adjudication, transition bridges | `../workers/W7-EMBEDDING-WORKER.md`, `W8-ASSEMBLER-WORKER.md` |

## Conventions (read before using any prompt)

1. **Placeholders** use `{{DOUBLE_BRACES}}`, matching the existing codebase style (`prompts.py` already does `{{CLARIFIED_SUMMARY}}`). Substitute with `.replace()`, never f-strings (evidence text contains braces).
2. **Every prompt that returns JSON** must be called with low temperature (given per prompt) and parsed through the same defensive path the codebase already uses: strip code fences → `json.loads` → validate types → on failure retry once → on second failure take the prompt's **On failure** action. Never let a parse error propagate out of a worker.
3. **Structural data separation:** anything that came from the internet (evidence quotes, scraped text, search snippets) is wrapped in `<evidence>`/`<data>` tags inside the prompt, and every such prompt carries the anti-injection line. This is a security control (`../11-SECURITY-PLAN.md` §6) — do not remove it to save tokens.
4. **Output contracts are law:** the *Output schema* block in each file is what the post-parse validator must enforce. If you change a schema, change the validator and the plan doc in the same PR.
5. **Model params:** default `llama-3.1-8b-instant` via the existing `generate_chat`. Where a prompt is quality-critical (claim auditor, executive summary) the file says so — those are the first candidates for a stronger model if audit scores are weak.
6. Keep prompts in code as module-level constants named exactly as given in each file (e.g. `CLARIFICATION_JUDGE_PROMPT`) so plan docs, code, and this library stay greppable to each other.
