# Research Worker

Contract Status: Implemented (partial persistence)

## MVP Boundary
- In scope: generate search queries, fetch SERP results, scrape web pages, persist source metadata and evidence snippets.
- Out of scope: complete Astra persistence and deep quality scoring.

## Endpoints and Methods
- Trigger chain starts after `outline_ready`.
- Internal task: `run_research(report_id: str)`.

## Request/Response Schema
- Internal input:
```json
{"report_id":"uuid"}
```
- Progress event:
```json
{"type":"searching_sources","payload":{"report_id":"uuid"}}
```
- Completion event:
```json
{"type":"research_done","payload":{"report_id":"uuid"}}
```
- Failure event:
```json
{"type":"research_failed","payload":{"report_id":"uuid","error":"message"}}
```

## Errors
- `Report not found`
- `Clarified summary missing`
- SERP provider errors (per-query continue-on-failure)
- scrape extraction empty/noisy content

## Service Method Signatures
```python
def run_research(report_id: str) -> None
def generate_queries(clarified_summary: str) -> list[str]
def search(query: str) -> list[dict]
def is_duplicate_url(report_id: str, url: str) -> bool
def create_source(report_id: str, result: dict) -> models.Source
def save_evidence(source_id: str, snippets: list[str]) -> None
def scrape_and_extract(url: str) -> tuple[list[str], str]
def save_to_astra(report_id: str, source_id: str, url: str, text: str, metadata: dict) -> None
```

## Examples
- `news` sources: save snippet evidence only.
- `patent` sources: metadata only.
- `web` sources: scrape, extract snippets, save metadata + snippets.

## What It Does Not Solve
- Does not currently persist to Astra (stub).
- Does not emit fine-grained progress phases yet.

## Happy Path
1. Receives `report_id` and loads clarified context.
2. Executes query fan-out; processes deduped results.
3. Emits `research_done` after persistence.

## Failure Path 1 (Provider instability)
1. Some query searches fail.
2. Worker logs and continues other queries.
3. Overall task still succeeds if enough results persist.

## Failure Path 2 (Hard task failure)
1. Core dependency failure causes unhandled exception.
2. Worker emits `research_failed`.
3. Celery retries task with backoff.

## Success and Acceptance Tests
- Given valid report + summary, emits `searching_sources` then `research_done`.
- Duplicate URLs are not inserted twice for same report.
- On forced fatal exception, emits `research_failed` with error.

## Implementation Preconditions
- SERP API credentials configured.
- Scraping utility and DB tables available.
- Redis pub/sub for progress events.

