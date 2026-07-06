# Trend Worker Implementation

Plan Type: Build-Later Blueprint

## Stubs/TODOs
- API: no direct endpoint for MVP.
- Worker: create `app/workers/trend_worker.py` with `run_trend(report_id)`.
- Service: add `TrendService` for source fetch + extraction.
- Persistence: write into `trends` table.
- Eventing: publish `trend_ready` / `trend_failed`.

## Assumptions
- Trend data from news/reports is enough for MVP.
- Time window defaults to last 90 days.

## Dependencies
- Query generation from clarified summary.
- Provider/API keys for trend sources.
- Trends schema and migration readiness.

## Edge Case List
- same trend repeated across multiple sources.
- stale trends outside time window.
- low-signal trends with weak evidence.

## Service Method Signatures
```python
def run_trend(report_id: str) -> None
def gather_trend_sources(context: str, days: int) -> list[dict]
def extract_trends(items: list[dict]) -> list[dict]
def persist_trends(report_id: str, trends: list[dict]) -> int
```

## Why This Structure
- Keeps trend extraction independent from research worker while sharing orchestration model.

## What Was Dropped and Why
- Time-series forecasting dropped due to MVP complexity.

## What Can Be Improved Later
- Trend confidence score and category taxonomy.

## Happy Path
1. Pull trend candidates.
2. Extract and dedupe.
3. Persist and emit `trend_ready`.

## Failure Path 1
1. Source provider unavailable.
2. Retry.
3. Emit `trend_failed`.

## Failure Path 2
1. Extraction yields zero valid trends.
2. Emit failure with reason.
3. Continue pipeline in degraded mode.

## Success and Acceptance Tests
- Minimum one trend stored for seeded test topic.
- Completion event emitted with count.
- Duplicate trend titles deduped per report.

