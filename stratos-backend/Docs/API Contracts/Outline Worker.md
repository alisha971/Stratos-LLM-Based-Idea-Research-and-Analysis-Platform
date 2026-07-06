# Outline Worker

Contract Status: Implemented

## MVP Boundary
- In scope: generate deterministic report sections from clarified summary and persist ordered sections.
- Out of scope: dynamic section-level personalization per user role.

## Endpoints and Methods
- Triggered indirectly after `POST /orchestrate/orchestrate/clarification/accept-consent`.
- Internal task: `run_outline(report_id: str)`.

## Request/Response Schema
- Consent request params: `session_id: str`
- Consent response:
```json
{"session_id":"uuid","status":"READY_FOR_RESEARCH","message":"Clarification accepted. Research can begin."}
```
- Internal input:
```json
{"report_id":"uuid"}
```
- Output event:
```json
{"type":"outline_ready","payload":{"report_id":"uuid","sections":[{"section_id":"uuid","title":"Problem Context & Validation","order_index":1}]}}
```

## Errors
- `404 Session not found`
- `400 Consent not requested`
- Worker errors: `Report not found`, `Clarified summary missing`, invalid outline JSON

## Service Method Signatures
```python
def accept_consent(db: Session, session: models.Session) -> None
def handle_outline_ready(db: Session, report_id: str, sections: list) -> None
def run_outline(report_id: str) -> None
def parse_outline(raw_output: str) -> list[str]
```

## Examples
- Input summary from `session.clarified_summary`.
- Parsed sections enforce core section set and optional section allowlist.

## What It Does Not Solve
- Does not verify section quality against external evidence.
- Does not produce report prose.

## Happy Path
1. Consent accepted, outline task queued.
2. Worker parses sections and writes ordered rows.
3. Emits `outline_ready`; orchestrator transitions and starts research.

## Failure Path 1 (Missing clarified summary)
1. Consent accepted for malformed/incomplete session data.
2. Worker raises `Clarified summary missing`.
3. Task retries then fails.

## Failure Path 2 (Invalid LLM structure)
1. LLM returns invalid JSON for sections.
2. Parser raises validation error.
3. Task retries then fails without emitting `outline_ready`.

## Success and Acceptance Tests
- For valid clarified summary, sections persisted in strict order.
- `outline_ready` includes report id and ordered section list.
- Duplicate rerun replaces existing sections idempotently.

## Implementation Preconditions
- Clarified summary persisted before task invocation.
- Report row exists and belongs to session.
- Redis pub/sub and Celery worker active.

