# Embedding Worker

Contract Status: Planned Contract (MVP target)

## MVP Boundary
- In scope: consume report chunks, generate embeddings, persist vectors.
- Out of scope: semantic reranking service and online query API.

## Endpoints and Methods
- Triggered per section chunk batch completion.
- Internal task: `run_embedding(report_id: str, chunk_ids: list[str])`.

## Request/Response Schema
```json
{"report_id":"uuid","chunk_ids":["uuid1","uuid2"]}
```
```json
{"type":"embedding_done","payload":{"report_id":"uuid","embedded_chunks":2}}
```

## Errors
- Missing chunk ids.
- embedding model/API failure.
- vector storage write failure.

## Service Method Signatures
```python
def run_embedding(report_id: str, chunk_ids: list[str]) -> None
def fetch_chunks(chunk_ids: list[str]) -> list[dict]
def generate_embeddings(texts: list[str]) -> list[list[float]]
def persist_vectors(report_id: str, vectors: list[dict]) -> int
```

## Expected Functionality
- Persist vector representations for all eligible chunks.

## Input/Output Contract
- Input: report and chunk identifiers.
- Output: vector records and completion event.

## Trigger and Completion Events
- Trigger: section chunk persistence.
- Completion: `embedding_done` or `embedding_failed`.

## Failure Semantics
- Batch retry for transient model failures.
- Partial success allowed with retry queue for failed chunks.

## What It Does Not Solve
- User-facing semantic search API.

## Happy Path
1. Load chunks.
2. Generate embeddings.
3. Persist vectors and emit `embedding_done`.

## Failure Path 1
1. Embedding provider times out.
2. Retry with backoff.
3. Emit `embedding_failed` on exhaustion.

## Failure Path 2
1. Vector DB write partially fails.
2. Persist successful subset.
3. Enqueue failed chunk ids for retry.

## Success and Acceptance Tests
- Every chunk gets one vector row with metadata.
- Completion event carries embedded count.
- Duplicate embedding writes prevented by idempotency key.

## MVP Exclusions
- ANN index tuning and recall benchmarking.
- multi-model embeddings.

## Implementation Preconditions
- Vector store collection and schema created.
- Embedding model config wired.
- chunk persistence stable.

