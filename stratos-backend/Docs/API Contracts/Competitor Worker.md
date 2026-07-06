# Competitor Worker

Contract Status: Planned Contract (MVP target)

## MVP Boundary
- In scope: discover competitor set, extract basic positioning/features/pricing metadata.
- Out of scope: deep benchmark scoring and exhaustive company profiles.

## Endpoints and Methods
- Triggered internally after `outline_ready`.
- Internal task: `run_competitor(report_id: str)`.

## Request/Response Schema
```json
{"report_id":"uuid","max_competitors":8}
```
```json
{"type":"competitor_done","payload":{"report_id":"uuid","competitor_count":6}}
```

## Errors
- Missing report context.
- extraction failures from noisy pages.
- duplicate/low-confidence competitor candidates.

## Service Method Signatures
```python
def run_competitor(report_id: str) -> None
def discover_competitors(context: str, max_competitors: int) -> list[dict]
def enrich_competitor(candidate: dict) -> dict
def persist_competitors(report_id: str, competitors: list[dict]) -> int
```

## Examples
- Input: report context + optional cap.
- Output: persisted competitor records + `competitor_done`.

## Expected Functionality
- Return a concise, deduplicated competitor landscape usable by section writing.

## Input/Output Contract
- Input: report context from clarified summary/outline.
- Output: competitor entities with source links and fields.

## Trigger and Completion Events
- Trigger: `outline_ready`.
- Completion: `competitor_done` or `competitor_failed`.

## Failure Semantics
- Retry for transient search/scraping failures.
- Persist partial successful competitors if threshold met.

## What It Does Not Solve
- Financial modeling or moat quantification.

## Happy Path
1. Discover candidate competitors.
2. Enrich metadata and dedupe.
3. Persist and emit `competitor_done`.

## Failure Path 1
1. No reliable competitors found.
2. Emit `competitor_failed`.
3. Continue pipeline with fallback narrative.

## Failure Path 2
1. Parsing errors on most candidate pages.
2. Persist only valid subset.
3. Emit degraded success metadata.

## Success and Acceptance Tests
- At least N valid competitor records persist for seeded context.
- Event payload carries count and report id.
- Duplicate competitor names/domains are deduped.

## MVP Exclusions
- Detailed product matrix across dozens of features.
- Pricing trend over time.

## Implementation Preconditions
- Competitor schema/table ready.
- Data extraction heuristics defined.
- Orchestrator completion gate updated for competitor stream.

