# Clarification Worker

Contract Status: Implemented

## MVP Boundary
- In scope: multi-turn clarification, schema accumulation, confidence scoring, ready signal.
- Out of scope: advanced contradiction resolution and semantic memory.

## Endpoints and Methods
- `POST /orchestrate/orchestrate/start-session`
- `POST /orchestrate/orchestrate/clarification/chat`
- Internal task: `run_clarification(session_id: str)`

## Request/Response Schema
- Start-session request params: `user_id: str`, `idea_description: str`
- Chat request params: `session_id: str`, `message: str`
- Start-session response:
```json
{"session_id":"uuid","report_id":"uuid","status":"CLARIFYING","message":"Session created. Clarification started."}
```
- Chat response:
```json
{"session_id":"uuid","status":"CLARIFYING"}
```

## Errors
- `404 Session not found`
- `400 Session not in clarification state`
- `500` worker failure after retries

## Service Method Signatures
```python
def start_session(db: Session, user_id: str, idea_description: str) -> tuple[Session, Report]
def start_clarification(db: Session, session: models.Session) -> None
def handle_user_message(db: Session, session: models.Session, message: str) -> None
def handle_clarification_ready(db: Session, session_id: str, payload: dict) -> None
def run_clarification(session_id: str) -> None
```

## Events and Examples
- Emits: `session_created`, `clarification_started`, `clarification_update`, `clarification_ready`, `clarification_consent_requested`.
- Example `clarification_update` payload includes `schema`, `confidence_score`, `mirror_summary`, `next_question`.

## What It Does Not Solve
- Does not guarantee perfect factual completeness.
- Does not enforce user authentication in current runtime.

## Happy Path
1. Session starts and first clarification question is generated.
2. User answers until confidence reaches threshold.
3. Worker emits `clarification_ready`; orchestrator requests consent.

## Failure Path 1 (LLM invalid JSON)
1. Worker receives malformed model output.
2. JSON extraction/parsing fails.
3. Task retries (up to 3); then surfaces failure.

## Failure Path 2 (Invalid session state)
1. User posts chat while session is not `CLARIFYING`.
2. API rejects request with `400`.
3. No worker execution occurs.

## Success and Acceptance Tests
- Given valid session + messages, worker emits `clarification_update` with monotonic confidence.
- At threshold, worker emits `clarification_ready` and orchestrator transitions to `AWAITING_CONSENT`.
- Chat call in invalid state returns `400`.

## Implementation Preconditions
- Redis pub/sub channel `stratos_events`.
- Celery worker and DB session availability.
- Clarification prompt configured.

