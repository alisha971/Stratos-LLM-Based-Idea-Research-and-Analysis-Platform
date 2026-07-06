# Assembler Worker

Contract Status: Planned Contract (MVP target)

## MVP Boundary
- In scope: consolidate section chunks into final report body and metadata.
- Out of scope: advanced editorial rewrite and design-heavy formatting.

## Endpoints and Methods
- Triggered after all section writing tasks complete.
- Internal task: `run_assembler(report_id: str)`.

## Request/Response Schema
```json
{"report_id":"uuid"}
```
```json
{"type":"report_ready_for_export","payload":{"report_id":"uuid","section_count":7}}
```

## Errors
- Missing sections/chunks.
- malformed citation links.
- persistence conflict.

## Service Method Signatures
```python
def run_assembler(report_id: str) -> None
def fetch_completed_sections(report_id: str) -> list[dict]
def merge_sections(sections: list[dict]) -> dict
def persist_report_draft(report_id: str, draft: dict) -> None
```

## Expected Functionality
- Produce a coherent, ordered final report draft.

## Input/Output Contract
- Input: completed section chunks and citations.
- Output: final draft artifact and export-ready event.

## Trigger and Completion Events
- Trigger: all `section_done` events received.
- Completion: `report_ready_for_export` or `assembler_failed`.

## Failure Semantics
- Retry on transient DB/LLM post-processing issues.
- Fail fast if required sections are missing.

## What It Does Not Solve
- Visual layout/export format rendering.

## Happy Path
1. Fetch all completed sections.
2. Merge and validate document structure.
3. Persist draft and emit export-ready event.

## Failure Path 1
1. One required section missing.
2. Emit `assembler_failed`.
3. Keep report in recoverable state.

## Failure Path 2
1. Citation integrity check fails.
2. Reject assembly output.
3. Trigger re-write/reconcile flow.

## Success and Acceptance Tests
- Final draft contains all required sections in order.
- Citations resolve to existing sources.
- Emits exactly one `report_ready_for_export`.

## MVP Exclusions
- Stylistic rewrite optimization.
- multi-format narrative variants.

## Implementation Preconditions
- Section writer completion gate in orchestrator.
- Draft storage field/table available.
- Citation validation utility ready.

