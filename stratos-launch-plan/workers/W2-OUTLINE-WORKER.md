# W2 — Outline Worker: Upgrade Plan

## 1. What it does today (plain language)

After the user approves the summary, this worker decides the report's table of contents — which sections the report will have. It lives in `app/workers/outline_worker.py`. It calls the LLM for an outline **but then mostly ignores the answer**: it always forces the same 7 hardcoded "core" sections and allows at most 3 extra ones from a fixed allowlist. Every report looks structurally identical, whether the idea is a B2B API or a street-food franchise.

## 2. Who it competes with (the quality bar)

Real analyst reports (CB Insights, Gartner market guides) and AI research products (Perplexity/OpenAI Deep Research, Stanford's STORM outline stage) adapt structure to the topic: a hardware idea gets "Supply Chain & Manufacturing", a regulated fintech idea gets "Regulatory Landscape". The bar: **the outline should feel like an expert chose it for THIS idea**, and the user should be able to adjust it before the expensive research starts.

## 3. Feature plan (do in order)

### O1 — Fix the null-ID event bug (from main plan B2.3)

`db.flush()` before building the `outline_ready` payload so every section has a real `section_id`. Do this first; later features depend on stable IDs.

### O2 — Report-type templates

- **File:** new `app/services/outline_templates.py` with 5 templates as plain Python dicts: `b2b_saas`, `b2c_product`, `marketplace`, `hardware`, `services`. Each template = 5 required sections + 6 candidate optional sections with one-line "include when…" criteria (e.g. `"Regulatory Landscape": "include when the idea touches finance, health, food, transport, or minors"`).
- The worker picks the template using the idea category stored by the clarification worker (W1 task C2); default to `b2c_product` if absent.

### O3 — LLM chooses within the template (structure + freedom)

- New prompt: given the clarified summary and the template, return JSON: the required sections (always), 2–4 selected optional sections **with a one-sentence reason each**, and for every section a 15–25-word `scope_note` describing what it should cover for THIS idea.
- Persist `scope_note` on the `Section` row (add a nullable column via Alembic migration). The section writer (W6) will use it as steering — this is the single biggest quality lever in this doc.
- Validation: reject and retry once if the LLM returns sections outside the template or fewer than 7 total; on second failure, fall back to required sections only (never fail the pipeline over an outline).

### O4 — User-editable outline (approval step)

- After `outline_ready`, pause the pipeline in a new state `AWAITING_OUTLINE_APPROVAL` (add to `SessionState`). New endpoints: `POST /orchestrate/outline/approve` and `POST /orchestrate/outline/edit` (`{report_id, remove_section_ids: [], add_titles: [], rename: {id: title}}`).
- Frontend shows the outline as a checklist with the LLM's reasons; one click approves. Add a 10-minute auto-approve timeout (Celery countdown task) so an inattentive user doesn't stall forever.
- Update `../05-INTEGRATION-CONTRACT.md` (new state, 2 endpoints, `outline_approved` event) in the same PR.

### O5 — Section dependency hints

- Add an `evidence_hints` JSON field per section in the template: which evidence types matter (`["market_size", "news", "competitors", "academic"]`). The evidence bundle service uses hints to weight ranking per section (competitor section pulls competitor insights first; trends section weights trend items). Small change in `evidence_bundle_service.py` — pass the hints into the ranker's scoring.

### O6 — Standalone product mode (optional)

`POST /v1/outline` with `{topic_summary, document_type}` → structured outline with scope notes and reasons. This is a sellable "document planner" API for writing tools. Thin router over existing logic.

## 4. Testing checklist (run all before production)

1. **Unit — template selection:** 5 canned clarified summaries (one per category) → correct template chosen; missing category → default template, no crash.
2. **Unit — validation fallback:** mock the LLM to return garbage twice → worker falls back to required-sections-only and emits `outline_ready` (pipeline survives).
3. **ID test:** run a real session → every section in the `outline_ready` payload has non-null `section_id`, and those IDs exist in Postgres.
4. **Differentiation eval (manual, the key one):** generate outlines for (a) "B2B fraud-detection API for banks", (b) "organic dog treats D2C brand", (c) "drone-based crop monitoring hardware". The three outlines must differ by ≥ 3 sections, and (a) must include a regulatory section, (c) a supply-chain/manufacturing section. Paste all three outlines in the PR.
5. **Approval flow:** approve, edit-then-approve, and timeout paths each tested via curl; state transitions match the contract doc; pipeline proceeds to research in all three.
6. **Scope note propagation:** after a full run, check one section's LLM context (log it at debug level) contains the scope note text.
7. **Regression:** full pipeline smoke passes.
