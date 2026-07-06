# Clarification Worker Implementation

Plan Type: As-built implementation

## Stubs/TODOs
- Add contradiction detection across turns.
- Add structured parse fallback telemetry.
- Add auth guard at API layer for chat routes.

## Assumptions
- Clarification schema fields are stable for MVP.
- Confidence threshold `0.95` is acceptable gate.

## Dependencies
- Celery + Redis pub/sub.
- LLM prompt/controller.
- `sessions` and `chat_messages` persistence.

## Edge Case List
- Empty LLM response.
- Invalid JSON output from LLM.
- Session deleted between enqueue and execution.

## Service Method Signatures
```python
def run_clarification(session_id: str) -> None
def merge_schema(existing: dict, incoming: dict) -> dict
def compute_confidence(schema: dict) -> float
```

## Why This Structure
- Stateless worker with persisted chat history keeps retries safe.

## What Was Dropped and Why
- Dynamic confidence model dropped for deterministic completion gate.

## What Can Be Improved Later
- Better schema contradiction handling and user intent disambiguation.

## Happy Path
1. Read chat history.
2. Merge schema and compute confidence.
3. Emit update; emit ready when threshold crossed.

## Failure Path 1
1. LLM output invalid.
2. Retry task.
3. Fail after retry budget.

## Failure Path 2
1. Session in invalid lifecycle state.
2. Ignore/exit safely.
3. No state mutation.

## Success and Acceptance Tests
- Confidence is monotonic for appended valid answers.
- `clarification_ready` emitted only above threshold.
- Consent request event carries full summary payload.

