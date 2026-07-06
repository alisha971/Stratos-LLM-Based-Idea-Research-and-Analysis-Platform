# Research Worker Implementation

Plan Type: As-built implementation (partial)

## Stubs/TODOs
- Implement `save_to_astra`.
- Add richer progress events.
- Add quality filters per source type.

## Assumptions
- Generated queries are adequate for MVP evidence coverage.
- Partial per-query failure is acceptable.

## Dependencies
- SERP provider integration.
- scraping/cleaning utilities.
- `sources` and `source_evidence` persistence.

## Edge Case List
- duplicate URLs.
- noisy pages with no extractable text.
- provider rate-limit bursts.

## Service Method Signatures
```python
def run_research(report_id: str) -> None
def generate_queries(clarified_summary: str) -> list[str]
def search(query: str) -> list[dict]
def scrape_and_extract(url: str) -> tuple[list[str], str]
```

## Why This Structure
- Query-level parallelism with sequential DB writes balances speed and safety.

## What Was Dropped and Why
- Full vector persistence was deferred to keep MVP ingestion functional quickly.

## What Can Be Improved Later
- Astra persistence, confidence scoring, and citation quality ranking.

## Happy Path
1. Generate queries.
2. Search and process results.
3. Persist evidence and emit `research_done`.

## Failure Path 1
1. Some queries fail.
2. Continue remaining queries.
3. Complete with partial evidence.

## Failure Path 2
1. Fatal exception occurs.
2. Emit `research_failed`.
3. Task retries with backoff.

## Success and Acceptance Tests
- Event flow: searching -> done/failed.
- No duplicate source URLs in report scope.
- Evidence rows persist for valid snippets.

