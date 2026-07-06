# Section Writer Worker

Contract Status: Planned Contract (MVP target)

## MVP Boundary
- In scope: generate section drafts from outline + evidence with inline citation references.
- Out of scope: advanced stylistic personalization and multi-version writing.

## Endpoints and Methods
- Triggered after research/trend/competitor completion gate.
- Internal task: `run_section_writer(report_id: str, section_id: str)`.

## Request/Response Schema
```json
{"report_id":"uuid","section_id":"uuid","context_bundle":{"sources":[],"trends":[],"competitors":[]}}
```
```json
{"type":"section_done","payload":{"report_id":"uuid","section_id":"uuid","chunk_count":3}}
```

## Errors
- Missing section/report.
- missing evidence bundle.
- generation quality validation failed.

## Service Method Signatures
```python
def run_section_writer(report_id: str, section_id: str) -> None
def build_section_context(report_id: str, section_id: str) -> dict
def generate_section_draft(context: dict) -> dict
def persist_section_chunks(section_id: str, chunks: list[dict]) -> int
```

## Examples
- Input: section id + evidence bundle.
- Output: `section_done` with chunk count and citations.

## Expected Functionality
- Produce grounded section chunks and citation links.

## Input/Output Contract
- Input: section metadata + fetched evidence.
- Output: stored chunks/citations + section completion event.

## Trigger and Completion Events
- Trigger: `research_done` + other required worker completions.
- Completion: `section_done` or `section_failed`.

## Failure Semantics
- Retry generation on transient model/provider errors.
- Mark section failed if context is insufficient.

## What It Does Not Solve
- Human editorial approval workflow.

## Happy Path
1. Build section context.
2. Generate grounded section.
3. Persist chunks/citations and emit `section_done`.

## Failure Path 1
1. Context bundle empty.
2. Emit `section_failed`.
3. Queue remediation/fallback section.

## Failure Path 2
1. Generated output misses citation structure.
2. Validation rejects payload.
3. Retry then fail with reason.

## Success and Acceptance Tests
- Generated chunks include source references.
- Section event emitted once with idempotency guard.
- Persisted chunk order deterministic.

## MVP Exclusions
- Multi-language report generation.
- Tone presets per persona.

## Implementation Preconditions
- Chunk/citation schemas active.
- Completion gate rules finalized.
- Prompt contract defined for grounded writing.

