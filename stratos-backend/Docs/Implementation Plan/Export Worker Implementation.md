# Export Worker Implementation

Plan Type: Build-Later Blueprint

## Stubs/TODOs
- Worker: create `app/workers/export_worker.py`.
- API: add export trigger endpoint (optional MVP route).
- Service: implement renderer interface.
- Persistence: write export metadata row.
- Eventing: emit `export_done` / `export_failed`.

## Assumptions
- Assembled report draft is available before export.
- PDF is mandatory MVP format; HTML optional.

## Dependencies
- Rendering library/toolchain.
- Export storage backend (local/S3).
- exports schema/migration.

## Edge Case List
- invalid format request.
- renderer crash on malformed content.
- storage write failure.

## Service Method Signatures
```python
def run_export(report_id: str, format: str = "pdf") -> None
def load_report_draft(report_id: str) -> dict
def render_export(draft: dict, format: str) -> str
def persist_export(report_id: str, format: str, path_or_url: str) -> str
```

## Why This Structure
- Isolates rendering from orchestrator and keeps export retry-safe.

## What Was Dropped and Why
- multi-format rendering presets beyond PDF deferred for MVP.

## What Can Be Improved Later
- branded templates, sharing permissions, and export versioning.

## Happy Path
1. Load draft.
2. Render PDF and store artifact.
3. Persist metadata and emit completion.

## Failure Path 1
1. Unsupported format.
2. Reject without enqueuing worker.
3. Return validation error.

## Failure Path 2
1. Renderer/storage transient failure.
2. Retry with backoff.
3. Emit `export_failed` after retries.

## Success and Acceptance Tests
- Valid report yields non-empty PDF artifact.
- Export metadata contains format and path/url.
- Completion event includes report and export ids.

