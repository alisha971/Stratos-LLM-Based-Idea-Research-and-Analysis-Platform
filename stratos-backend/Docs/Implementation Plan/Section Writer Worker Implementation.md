# Section Writer Worker Implementation

Plan Type: Build-Later Blueprint

## Stubs/TODOs
- Worker: create `app/workers/section_worker.py`.
- Service: add `SectionWriterService`.
- Persistence: write `report_chunks` and `citations`.
- Eventing: emit `section_done` / `section_failed`.

## Assumptions
- Outline sections are finalized before writing.
- Evidence from research/trend/competitor is available.

## Dependencies
- Source evidence access layer.
- prompt contract for grounded generation.
- chunk/citation schema readiness.

## Edge Case List
- insufficient evidence for a section.
- hallucinated citations.
- chunk order inconsistency.

## Service Method Signatures
```python
def run_section_writer(report_id: str, section_id: str) -> None
def build_section_context(report_id: str, section_id: str) -> dict
def generate_section_draft(context: dict) -> dict
def persist_section_chunks(section_id: str, chunks: list[dict]) -> int
```

## Why This Structure
- Per-section tasking supports parallelism and retries with bounded blast radius.

## What Was Dropped and Why
- Human-in-the-loop editing workflow dropped for MVP simplicity.

## What Can Be Improved Later
- style controls, section-level confidence score, streaming deltas.

## Happy Path
1. Build section context.
2. Generate citation-grounded chunks.
3. Persist and emit `section_done`.

## Failure Path 1
1. Missing evidence bundle.
2. Emit `section_failed`.
3. Request fallback section generation.

## Failure Path 2
1. Citation validation fails.
2. Reject and retry generation.
3. Mark section failed after retries.

## Success and Acceptance Tests
- Every chunk has source references.
- Section completion idempotent on retries.
- Chunk ordering deterministic by `order_index`.

