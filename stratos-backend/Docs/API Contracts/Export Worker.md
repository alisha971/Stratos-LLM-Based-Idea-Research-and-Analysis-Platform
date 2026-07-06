# Export Worker

Contract Status: Planned Contract (MVP target)

## MVP Boundary
- In scope: export report draft to PDF/HTML and persist export metadata.
- Out of scope: branded theming variants and multi-language export packs.

## Endpoints and Methods
- Optional API trigger: `POST /orchestrate/orchestrate/export` (planned).
- Internal task: `run_export(report_id: str, format: str = "pdf")`.

## Request/Response Schema
```json
{"report_id":"uuid","format":"pdf"}
```
```json
{"export_id":"uuid","report_id":"uuid","format":"pdf","download_url":"https://..."}
```

## Errors
- invalid format.
- missing report draft.
- renderer failure.

## Service Method Signatures
```python
def run_export(report_id: str, format: str = "pdf") -> None
def load_report_draft(report_id: str) -> dict
def render_export(draft: dict, format: str) -> str
def persist_export(report_id: str, format: str, path_or_url: str) -> str
```

## Expected Functionality
- Generate downloadable artifact for final report.

## Input/Output Contract
- Input: report id and format.
- Output: export record and completion event.

## Trigger and Completion Events
- Trigger: `report_ready_for_export` or user export request.
- Completion: `export_done` or `export_failed`.

## Failure Semantics
- Retry renderer/storage transient errors.
- Emit terminal failure with actionable error reason.

## What It Does Not Solve
- Distribution workflows (email/share links with auth).

## Happy Path
1. Load report draft.
2. Render and store file.
3. Persist export row and emit `export_done`.

## Failure Path 1
1. Unsupported format requested.
2. Reject with validation error.
3. No worker task enqueued.

## Failure Path 2
1. Renderer crashes.
2. Retry with backoff.
3. Emit `export_failed` after max retries.

## Success and Acceptance Tests
- Generates non-empty PDF for valid report.
- Persists export metadata with retrievable URL/path.
- Emits completion event with export id.

## MVP Exclusions
- collaborative sharing controls.
- watermark/versioning controls.

## Implementation Preconditions
- Report draft persistence implemented.
- Render engine dependency selected.
- Export storage target configured.

