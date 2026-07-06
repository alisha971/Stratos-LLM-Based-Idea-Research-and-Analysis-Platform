# Post-MVP Improvements and Exclusions

Status: Deferred roadmap

## Intentional MVP Exclusions
- Advanced auth hardening and fine-grained authorization.
- Full deep-dive follow-up query/retrieval UX.
- Rich observability dashboards and SLO automation.
- advanced narrative styling and report design controls.
- multi-format export bundles beyond core PDF.

## Why These Were Deferred
- They do not block baseline end-to-end functionality.
- They add substantial infra/QA complexity relative to MVP value.
- They can be safely layered after worker contracts are stable.

## Post-MVP Improvement Backlog

### Platform and reliability
- Normalize route prefixes and enforce JWT dependencies.
- Add contract versioning strategy for events and payload schemas.
- Add idempotency keys and DLQ strategy across all workers.
- Add timeout budgets and retry class policies by worker.

### Data and quality
- Implement Astra persistence for research/embedding paths.
- Add citation quality scoring and hallucination checks.
- Add trend and competitor confidence metrics.
- Introduce report quality rubric and automatic checks.

### User-facing capabilities
- Deep-dive Q&A on generated report with retrieval.
- Better export formatting/templates and share workflows.
- Role/persona-based section tone controls.

## Deferred by Worker
- **Clarification**: richer contradiction resolution, adaptive questioning.
- **Outline**: dynamic section strategy by domain vertical.
- **Research**: richer progress taxonomy and source reliability scoring.
- **Trend**: longitudinal trend movement and confidence.
- **Competitor**: deeper feature matrix and pricing history.
- **Section Writer**: style variants and iterative rewrite loop.
- **Embedding**: ANN indexing strategy and retrieval tuning.
- **Assembler**: automated readability and consistency passes.
- **Export**: HTML/docx variants and access controls.

## Re-entry Criteria for Deferred Items
- Core pipeline is stable in CI with deterministic acceptance tests.
- Event contracts frozen at MVP v1.
- Observed user usage justifies next-layer investment.

