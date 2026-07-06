# W7 — Embedding Worker: Build Plan (from stub)

## 1. What it does today (plain language)

Nothing. `app/workers/embedding_worker.py` is an intentional no-op: the section worker enqueues it after each section, and it just publishes an `embedding_skipped` event. It was parked because the MVP report doesn't need vectors.

**Why build it now:** it unlocks the two features that make Stratos sticky and paid-tier-worthy — **Deep Dive Q&A** ("chat with your report": ask follow-up questions answered from the report's own evidence) and **semantic retrieval** for the section writer (find evidence by meaning, not keywords). It also enables cross-report dedupe.

## 2. Who it competes with (the quality bar)

Standalone this is a **RAG-as-a-service pipeline** — the territory of LlamaIndex/LangChain hosted offerings, Pinecone-based starter kits, and "chat with your PDF" products (ChatPDF, Humata). Their bar: answers grounded in the indexed content with quoted sources, sub-2-second retrieval, honest "I don't know" when the corpus lacks the answer.

## 3. Feature plan (do in order)

### E1 — Choose and wire an embedding model

- **Decision (make it once, in code comments):** hosted-API-first: OpenAI `text-embedding-3-small` (cheap: ~$0.02 per 1M tokens; re-add `openai` to requirements — it was pruned as unused) with env `EMBEDDING_PROVIDER=openai`. Provide a local fallback `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim, free, CPU-fine) behind `EMBEDDING_PROVIDER=local` for zero-cost dev. Abstract in new `app/services/embedding_service.py`: `embed_texts(list[str]) -> list[list[float]]` with batching (≤ 96 texts/call) and retry.
- **Important dimension note:** collection dimension must match the provider (1536 vs 384). Store the provider name in the collection name (`embeddings_openai_1536`) so switching providers can't silently mix spaces.

### E2 — Astra vector collection + writer

- `astra_evidence_repository.py`: add `create/get vector collection` (astrapy supports `$vector`), and `save_embeddings(docs)` where each doc = `{_id, report_id, section_id?, kind: evidence|chunk|trend, text, url?, $vector}`.
- Rewrite `embedding_worker.py`: on `run_embedding(report_id, section_id)` — fetch the section's persisted chunks + that section's evidence texts, embed, upsert. Emit `embedding_done` (`{session_id, report_id, section_id, vectors_count}`) replacing `embedding_skipped` (update contract doc + frontend union; keep `embedding_skipped` for the no-creds fail-soft path).

### E3 — Retrieval service

- `embedding_service.py`: `search(report_id, query, k=8, kind=None) -> list[{text, url, score, kind}]` via Astra vector `$vector` similarity with a `report_id` filter. Unit-testable against a mocked repository.

### E4 — Deep Dive Q&A endpoint (the user-facing payoff)

- New `POST /reports/{report_id}/deep-dive` with `{question}` (JWT + ownership + plan gate — Pro-tier only, per doc 08 plans):
  1. Embed the question, retrieve top-8 across `chunk` + `evidence` kinds.
  2. LLM prompt: "Answer using ONLY these excerpts. Quote sources by URL. If the excerpts don't contain the answer, say what's missing and suggest what to research." Return `{answer, sources: [{url, quote}]}`.
  3. Stream it: reuse the SSE channel with `deepdive_chunk` events, or return non-streamed JSON for v1 (simpler — do that first).
- Frontend: a question box under the finished report (visible to Pro; upsell card for others).

### E5 — Semantic evidence retrieval for the section writer (quality feedback loop)

- In `evidence_bundle_service.py`: when building a section's bundle, if embeddings exist for the report's evidence (E2 runs on research completion too — add a bulk `run_embedding_bulk(report_id)` dispatched after `research_done`), blend rankings: `final = 0.5 × semantic_similarity(scope_note, evidence) + 0.3 × credibility + 0.2 × keyword`. Fall back to the existing ranker when vectors are absent. This directly raises section relevance.

### E6 — Near-duplicate collapse

- During bulk embedding, cosine-compare within the report's evidence; pairs > 0.95 → keep the higher-credibility one, flag the other `duplicate_of`. Stops the writer citing the same syndicated article twice.

### E7 — Standalone product mode (optional)

`POST /v1/index` + `POST /v1/query` over arbitrary user documents = a minimal RAG API. Only do this if pursuing the API business line (W3/W4/W5 standalone modes first — they're more differentiated).

## 4. Testing checklist (run all before production)

1. **Provider unit tests:** mock both providers → identical output shape; batching (250 texts → 3 API calls for openai batch size 96); provider failure → retry then `embedding_skipped` fail-soft (pipeline unaffected).
2. **Dimension safety test:** attempt to write a 384-dim vector to the 1536 collection → must raise loudly (not silently store) — assert the guard exists.
3. **Retrieval sanity:** index 20 fixture texts (10 about EV charging, 10 about bakery franchises); query "electric vehicle charging demand" → top-5 are all EV texts (score check, mocked or against a real dev Astra).
4. **Deep Dive grounding (release blocker):** index a fixture report; ask (a) a question the report answers → answer contains the fact + at least one source URL from the fixtures; (b) a question the report does NOT cover ("what is the CEO's name?") → answer must decline, zero invented facts. Run (b) 3 times.
5. **Plan gate test:** free-tier JWT calling deep-dive → 402/403 per contract; Pro JWT → 200.
6. **Dedupe test:** two near-identical fixture articles → one flagged `duplicate_of`; both distinct articles survive.
7. **Latency:** deep-dive p50 ≤ 4 s end-to-end (retrieval ≤ 1 s).
8. **Cost log:** embedding a full report (≈ 100 texts) logs token count; assert < $0.01 at openai pricing.
9. **Regression:** pipeline smoke passes with `EMBEDDING_PROVIDER` unset (skip path) AND set (real path).
