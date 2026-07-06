# Trend Worker

Contract Status: Planned Contract (MVP target)

## MVP Boundary
- In scope: collect trend evidence (news/reports/social signals), normalize into trend entities, link to report.
- Out of scope: predictive forecasting and real-time stream monitoring.

## Endpoints and Methods
- Triggered internally after `outline_ready`.
- Internal task: `run_trend(report_id: str)`.

## Request/Response Schema
```json
{"report_id":"uuid","focus_topics":["string"],"time_window_days":90}
```
```json
{"type":"trend_ready","payload":{"report_id":"uuid","trend_count":12}}
```

## Errors
- Missing report or summary context.
- Provider/API throttling.
- Empty trend extraction.

## Service Method Signatures
```python
def run_trend(report_id: str) -> None
def gather_trend_sources(context: str, time_window_days: int) -> list[dict]
def extract_trends(items: list[dict]) -> list[dict]
def persist_trends(report_id: str, trends: list[dict]) -> int
```

## Examples
- Input: `report_id` + focus keywords derived from clarified summary.
- Output event: `trend_ready` with aggregate counts.

## Expected Functionality
- Produce a bounded set of deduplicated trends relevant to report topic.

## Input/Output Contract
- Input: report context and optional topic filters.
- Output: trend entities in DB + completion event.

## Trigger and Completion Events
- Trigger: `outline_ready`.
- Completion: `trend_ready` or `trend_failed`.

## Failure Semantics
- Retry transient provider failures.
- Continue partial ingestion when some sources fail.

## What It Does Not Solve
- Longitudinal trend confidence scoring across quarters.

## Happy Path
1. Fetch trend sources.
2. Extract and dedupe trends.
3. Persist trends and emit `trend_ready`.

## Failure Path 1
1. Provider timeout.
2. Retries with backoff.
3. Emits `trend_failed` after max retries.

## Failure Path 2
1. No valid trends extracted.
2. Emits `trend_failed` with reason.
3. Orchestrator decides fallback path.

## Success and Acceptance Tests
- Given seeded context, at least one trend entity persists.
- Event payload includes `report_id` and trend count.
- Duplicate trends are not inserted in same report scope.

## MVP Exclusions
- Sentiment trajectory graphs.
- Regional trend segmentation.

## Implementation Preconditions
- Trend source connectors selected.
- `trends` table/collection schema finalized.
- Orchestrator fan-out includes trend task.

