# Embedding Worker Implementation

Plan Type: Build-Later Blueprint

## Stubs/TODOs
- Worker: create `app/workers/embedding_worker.py`.
- Service: add embedding generation wrapper.
- Persistence: Astra/vector store write with metadata.
- Eventing: publish `embedding_done` / `embedding_failed`.

## Assumptions
- Chunk text is stable post section writer completion.
- One embedding model is enough for MVP.

## Dependencies
- Embedding provider key.
- Vector schema/collection in Astra (or selected store).
- Chunk ids passed by writer/orchestrator.

## Edge Case List
- model dimension mismatch.
- oversized chunk payloads.
- vector write partial failures.

## Service Method Signatures
```python
def run_embedding(report_id: str, chunk_ids: list[str]) -> None
def fetch_chunks(chunk_ids: list[str]) -> list[dict]
def generate_embeddings(texts: list[str]) -> list[list[float]]
def persist_vectors(report_id: str, vectors: list[dict]) -> int
```

## Why This Structure
- Batch embeddings reduce provider overhead and maintain retry locality.

## What Was Dropped and Why
- Reranking/index optimization deferred until retrieval features are active.

## What Can Be Improved Later
- adaptive chunking and model fallback strategy.

## Happy Path
1. Fetch chunk batch.
2. Generate vectors.
3. Persist and emit completion.

## Failure Path 1
1. Provider timeout.
2. Retry batch.
3. Emit failure on exhaustion.

## Failure Path 2
1. Vector store write partially fails.
2. Commit successful subset.
3. Requeue failed chunk ids.

## Success and Acceptance Tests
- All chunk ids in request have vector records.
- Metadata binds vectors to report + section ids.
- Duplicate writes prevented through idempotency key.

