# Outline Worker Implementation

Plan Type: As-built implementation

## Stubs/TODOs
- Move section names to config for easier iteration.
- Add explicit `outline_failed` event.
- Add schema validation metrics.

## Assumptions
- Clarified summary is present before outline trigger.
- Core section list should always be included.

## Dependencies
- LLM outline prompt.
- `reports` and `sections` tables.
- Redis for `outline_ready`.

## Edge Case List
- Invalid JSON from LLM.
- Duplicate section titles.
- report missing at task runtime.

## Service Method Signatures
```python
def run_outline(report_id: str) -> None
def parse_outline(raw_output: str) -> list[str]
def handle_outline_ready(db: Session, report_id: str, sections: list) -> None
```

## Why This Structure
- Deterministic core section enforcement keeps downstream workers stable.

## What Was Dropped and Why
- Fully dynamic outlines dropped to reduce orchestration complexity.

## What Can Be Improved Later
- Confidence scoring for section relevance.

## Happy Path
1. Generate outline JSON.
2. Parse and persist sections idempotently.
3. Emit `outline_ready`.

## Failure Path 1
1. Missing summary.
2. Task raises and retries.
3. No section rows committed.

## Failure Path 2
1. LLM response malformed.
2. Parse fails.
3. Retry then fail.

## Success and Acceptance Tests
- Core sections always present.
- Re-run replaces prior section set.
- Event includes section ids and order indices.

