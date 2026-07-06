# Assembler Worker Implementation

Plan Type: Build-Later Blueprint

## Stubs/TODOs
- Worker: create `app/workers/assembler_worker.py`.
- Service: implement assembly and validation pipeline.
- Persistence: final draft field/table updates.
- Eventing: emit `report_ready_for_export` / `assembler_failed`.

## Assumptions
- Required sections list is fixed for MVP.
- Section chunks and citations are complete before assembly.

## Dependencies
- Section writer completion gate.
- Draft persistence location in DB.
- citation integrity validator.

## Edge Case List
- missing required section.
- broken citation references.
- section order mismatch.

## Service Method Signatures
```python
def run_assembler(report_id: str) -> None
def fetch_completed_sections(report_id: str) -> list[dict]
def merge_sections(sections: list[dict]) -> dict
def persist_report_draft(report_id: str, draft: dict) -> None
```

## Why This Structure
- Single assembly point ensures report consistency before export.

## What Was Dropped and Why
- LLM polishing pass deferred to keep deterministic assembly first.

## What Can Be Improved Later
- readability scoring and style harmonization.

## Happy Path
1. Pull completed sections.
2. Assemble deterministic report draft.
3. Persist and emit export-ready event.

## Failure Path 1
1. Missing section detected.
2. Emit `assembler_failed`.
3. Keep report recoverable for retries.

## Failure Path 2
1. Citation link invalid.
2. Reject draft.
3. Trigger section remediation.

## Success and Acceptance Tests
- Final draft contains required sections in order.
- Citation references resolve to persisted sources.
- Exactly one completion event emitted.

