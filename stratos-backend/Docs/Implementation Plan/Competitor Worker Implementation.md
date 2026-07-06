# Competitor Worker Implementation

Plan Type: Build-Later Blueprint

## Stubs/TODOs
- Worker: create `app/workers/competitor_worker.py`.
- Service: implement `CompetitorService`.
- Persistence: write to competitors table.
- Eventing: publish `competitor_done` / `competitor_failed`.

## Assumptions
- Competitor set capped at top 5-8 for MVP.
- Domain/name dedupe is sufficient initially.

## Dependencies
- Search/discovery provider.
- competitor schema fields finalized.
- orchestrator fan-out and fan-in hooks.

## Edge Case List
- false-positive competitor candidates.
- missing pricing data.
- conflicting feature claims.

## Service Method Signatures
```python
def run_competitor(report_id: str) -> None
def discover_competitors(context: str, max_items: int) -> list[dict]
def enrich_competitor(candidate: dict) -> dict
def persist_competitors(report_id: str, competitors: list[dict]) -> int
```

## Why This Structure
- Dedicated service isolates noisy extraction logic from orchestrator path.

## What Was Dropped and Why
- Deep comparative scoring dropped for MVP speed.

## What Can Be Improved Later
- richer feature matrix and confidence scoring.

## Happy Path
1. Discover candidates.
2. Enrich and dedupe.
3. Persist and emit completion.

## Failure Path 1
1. No valid candidates found.
2. Emit `competitor_failed`.
3. Continue with fallback narrative.

## Failure Path 2
1. Partial enrichment failures.
2. Persist valid subset.
3. Emit degraded-success metadata.

## Success and Acceptance Tests
- Stored competitor rows include source URL + name.
- Dedupe prevents duplicate competitor domains.
- Completion event includes `competitor_count`.

