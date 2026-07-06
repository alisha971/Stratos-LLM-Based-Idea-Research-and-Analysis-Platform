# W1 — Clarification Worker: Upgrade Plan

## 1. What it does today (plain language)

When a user types an idea like "an app for dog food", this worker plays the role of an interviewer. It asks follow-up questions ("Which country? Who pays? Subscription or one-time?") until it is confident it understands the idea, then writes a summary and asks the user to approve it. It lives in `app/workers/clarification_worker.py` and works well already.

**Its weakness:** "confidence" is computed by **counting how many schema fields are filled** (a field-count score reaching 0.95). This means it can be confident while completely misunderstanding the idea, and it can't tell a vague answer from a precise one. It also asks questions in a fixed style and never adapts to what kind of business the idea is.

## 2. Who it competes with (the quality bar)

Standalone, this is an **AI intake/requirements-elicitation engine** — the same job done by Typeform's AI forms, Intercom's Fin intake flows, and the interview stage of ChatGPT Deep Research / Perplexity Deep Research (which asks 1–3 sharp clarifying questions before researching). The bar those products set:

- Questions feel **specific to your input**, never generic.
- They ask **few** questions (3–5), not a long interrogation.
- They correctly stop when enough is known — and know **what** they still don't know.

## 3. Feature plan (do in order)

### C1 — Semantic confidence scoring (replaces field counting)

- **File:** `app/workers/clarification_worker.py` (`compute_confidence`), `app/llm/prompts.py`.
- After each user answer, make one extra LLM call with a **judge prompt**: given the accumulated schema, return JSON `{"coverage": {"audience": 0-1, "geography": 0-1, "problem": 0-1, "monetization": 0-1, "differentiation": 0-1}, "ambiguities": ["..."], "ready": true/false}`. Confidence = the minimum of the five coverage scores (a chain is as strong as its weakest link).
- Stop when `ready` is true AND min coverage ≥ 0.8, OR after 6 questions (hard cap — never annoy the user).
- Keep the old field-count as a fallback if the judge call fails (wrap in try/except, log the failure).

### C2 — Adaptive question selection

- Add to the question-generation prompt: the `ambiguities` list from C1 and the instruction "Ask about the single most important ambiguity only. One question. Max 25 words. Reference the user's own wording." Include 2 few-shot examples in the prompt (one B2B SaaS idea, one D2C product idea).
- Detect idea category in the first turn (B2B / B2C / marketplace / hardware / services — a single cheap LLM classification) and store it in the schema; the category tunes which coverage fields matter (e.g. hardware → supply chain question replaces monetization).

### C3 — Multi-answer parsing

- Users often answer three questions in one message ("US market, B2C, we charge $10/mo"). Today each turn maps to one field. Change the schema-merge prompt to extract **all** fields present in the answer, not just the one asked about. This alone cuts average question count by ~2.

### C4 — Skip-ahead for detailed inputs

- If the user's *initial* idea description already scores min-coverage ≥ 0.8 in C1's judge, skip questioning entirely and go straight to the consent summary ("You gave me a lot of detail — here's what I understood…"). Power users will love this; it's also what Deep Research products do.

### C5 — Editable consent summary

- Today consent is approve/reject. Add: the `clarification_consent_requested` payload carries the structured schema, and a new endpoint `POST /orchestrate/clarification/edit-summary` accepts `{session_id, edits: {field: value}}`, merges, regenerates the summary, and re-requests consent. (Update `../05-INTEGRATION-CONTRACT.md`; frontend adds inline-editable fields on the consent card.)

### C6 — Standalone product mode (optional, after all above)

Expose the worker as an independent API: `POST /v1/clarify` with `{domain_schema, conversation}` → `{next_question | done, structured_output, confidence}`. This is a sellable "AI intake engine" for any form/onboarding product. Requires only a thin new router — the worker logic is already conversation-in/schema-out.

## 4. Testing checklist (a smaller AI model must run all of these and paste results before production)

Create `tests/test_clarification_quality.py` plus a manual eval sheet.

1. **Unit — judge parsing:** feed the judge 3 canned LLM responses (valid JSON, malformed JSON, missing keys) → valid parses, malformed falls back to field-count without crashing.
2. **Cap test:** simulate a user who answers "I don't know" 10 times → worker must stop at 6 questions and proceed to consent with a "based on limited information" note.
3. **Skip test:** submit this exact idea: *"A B2C subscription app ($12/mo) for diabetic meal planning in the US, targeting adults 40+, differentiated by CGM integration"* → worker must ask **zero or one** question before consent.
4. **Multi-answer test:** first question asked, reply *"US, B2C, $10/month subscription"* → schema must show geography, audience-type, and monetization all filled after ONE turn.
5. **Eval set (manual, 10 ideas):** run 10 diverse ideas (list them in the PR: 3 B2B, 3 B2C, 2 marketplace, 1 hardware, 1 services). Record: number of questions asked (target average ≤ 4), and a human/LLM judgment "did the final summary faithfully represent the idea?" (target 10/10 faithful — any unfaithful summary is a release blocker).
6. **Regression:** full pipeline smoke script still passes; `clarification_update` / `clarification_consent_requested` event shapes unchanged (or contract doc updated).
