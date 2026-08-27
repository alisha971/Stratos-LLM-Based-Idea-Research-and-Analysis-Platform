---
name: MVP Implementation Docs Plan
overview: Create an as-built MVP documentation foundation from current runtime contracts first, then expand to full-pipeline worker implementation docs and subplans. Every worker doc will follow a strict template with contracts, flows, failures, tests, and explicit non-goals.
todos:
  - id: baseline-doc
    content: Create runtime-baseline doc and mismatch register
    status: completed
  - id: template-standard
    content: Define and lock shared worker documentation template
    status: completed
  - id: api-contracts-9workers
    content: Produce/normalize API contracts for all 9 workers
    status: completed
  - id: impl-plans-9workers
    content: Produce/normalize implementation plans and subplans for all 9 workers
    status: completed
  - id: integration-tests-plan
    content: Create cross-worker integration and acceptance test matrix
    status: completed
  - id: deferred-roadmap
    content: Document post-MVP improvements and exclusions rationale
    status: completed
isProject: false
---

# MVP Implementation Documentation Plan

## Planning Decisions Locked
- Source of truth for first pass: **runtime code as-built**.
- Worker scope to document in this phase: **full pipeline** (Clarification, Outline, Research, Trend, Competitor, Section Writer, Embedding, Assembler, Export).
- API baseline style: **document runtime exactly**, add fixes as TODOs.

## Phase 0 - Normalize the Baseline (single source of truth)
- Create a "Current Runtime Contract Baseline" doc that captures exactly what is currently implemented and callable.
- Use these references as inputs:
  - [C:/Users/hp/Desktop/VS/stratos/README.md](C:/Users/hp/Desktop/VS/stratos/README.md)
  - [C:/Users/hp/Desktop/VS/stratos/architecture.md](C:/Users/hp/Desktop/VS/stratos/architecture.md)
  - [C:/Users/hp/Desktop/VS/stratos/stratos-backend/Docs/System Design Brief.md](C:/Users/hp/Desktop/VS/stratos/stratos-backend/Docs/System%20Design%20Brief.md)
  - [C:/Users/hp/Desktop/VS/stratos/stratos-backend/Docs/Low-Level Architecture - Workers.md](C:/Users/hp/Desktop/VS/stratos/stratos-backend/Docs/Low-Level%20Architecture%20-%20Workers.md)
  - [C:/Users/hp/Desktop/VS/stratos/stratos-backend/Docs/API Contracts/API Contracts.md](C:/Users/hp/Desktop/VS/stratos/stratos-backend/Docs/API%20Contracts/API%20Contracts.md)
  - [C:/Users/hp/Desktop/VS/stratos/stratos-backend/Docs/Implementation Plan/Implementation Plan.md](C:/Users/hp/Desktop/VS/stratos/stratos-backend/Docs/Implementation%20Plan/Implementation%20Plan.md)
- Add an explicit "Known Contract Mismatches" section (e.g., route prefix/auth expectations/worker inventory drift) with owner and resolution target.

## Phase 1 - Standardize the Documentation Template
- Define one shared per-worker template used by both API Contract and Implementation Plan docs.
- Required sections per worker (from your structure):
  - endpoints
  - methods
  - req/res schema
  - errors
  - service method signatures
  - examples
  - what it does not solve
  - 1 happy path
  - 2 failure paths
  - success and acceptance tests
  - Stubs/TODOs
  - Assumptions
  - dependencies
  - edge case list
  - Why this structure
  - What was dropped and why
  - What can be improved later
- Add a fixed "MVP Boundary" subsection in each worker doc so scope is explicit.

## Phase 2 - Publish Worker API Contracts (as-built first, planned where missing)
- Finalize/update contract docs in this order:
  1) Clarification
  2) Outline
  3) Research
  4) Trend
  5) Competitor
  6) Section Writer
  7) Embedding
  8) Assembler
  9) Export
- For implemented workers: mark schema/status as **Implemented** with current payloads/events.
- For not-yet-implemented workers: mark as **Planned Contract (MVP target)** and include minimal viable contract only.
- For each unimplemented worker contract, add a fixed subsection:
  - **Expected Functionality**
  - **Input/Output Contract**
  - **Trigger and Completion Events**
  - **Failure Semantics**
  - **MVP Exclusions**
  - **Implementation Preconditions**

## Phase 3 - Publish Worker Implementation Plans + Subplans
- For each worker, produce implementation plan docs aligned to the same contract sections, then add worker-specific subplans:
  - Clarification: confidence accumulation + deterministic stop/handoff checks
  - Outline: section schema constraints + idempotent section upsert
  - Research: query generation + SERP + scrape pipeline + evidence persistence
  - Trend: source selection + dedupe + trend entity extraction
  - Competitor: competitor discovery + feature/pricing extraction
  - Section Writer: citation-grounded section generation
  - Embedding: chunking/embedding/index write path
  - Assembler: final report composition and consistency checks
  - Export: PDF/HTML rendering + metadata persistence
- Each subplan includes: dependencies, rollout order, fallback behavior, and acceptance gates.
- For workers without implementation, plans are authored as **Build-Later Blueprints** (design-to-build docs), not execution logs. Each blueprint must include:
  - **Stubs/TODOs mapped to code modules** (API, worker task, service layer, persistence)
  - **Assumptions to validate before coding**
  - **Dependency readiness checklist** (external APIs, queues, schemas, env vars)
  - **Edge-case handling list**
  - **Why this structure was chosen**
  - **What is dropped for MVP and why**
  - **Future improvements after MVP**

## Phase 3A - Unimplemented Worker Blueprint Order
- Author and review build-later plans in dependency order:
  1) Trend Worker
  2) Competitor Worker
  3) Section Writer Worker
  4) Embedding Worker
  5) Assembler Worker
  6) Export Worker
- Exit criteria for each blueprint:
  - service method signatures are frozen
  - request/response + event schemas are testable
  - one happy path + two failure paths are documented
  - worker-level acceptance tests are listed and executable once implemented

## Phase 4 - Cross-Worker Integration and Test Plan
- Create an integration plan that ties worker outputs and events into one end-to-end MVP pipeline.
- Add acceptance matrix levels:
  - worker-level happy/failure tests
  - orchestrator transition tests
  - end-to-end session-to-report test
- Define what constitutes MVP done:
  - core pipeline completes deterministically
  - expected events emitted
  - required artifacts persisted
  - error paths observable and recoverable

## Phase 5 - Roadmap and Deferred Improvements
- Add a "Post-MVP Improvements" doc capturing deferred items (non-blocking quality/perf enhancements).
- Track deliberate exclusions and rationale per worker to prevent scope creep.

## Deliverables to Produce
- Updated/created API contract docs for 9 workers.
- Updated/created implementation plan docs for 9 workers.
- Cross-worker integration and acceptance test plan.
- Known mismatch register with remediation order.
- Deferred improvements backlog.

## Core Assumptions
- Current runtime behavior is authoritative for v1 docs.
- Full pipeline docs can include planned workers even when implementation is pending.
- MVP contracts for pending workers should be minimal, testable, and backward-compatible with current orchestrator direction.

## Why This Structure
- Starts from factual runtime to avoid invalid docs.
- Uses one template across all workers for consistency and review speed.
- Separates immediate MVP functionality from future enhancements while still planning the full pipeline.

## Dropped From Initial Pass (intentionally)
- Deep optimization, scaling, and advanced observability design beyond MVP acceptance criteria.
- Non-essential optional UX/report embellishments not required for end-to-end pipeline completion.

## Improvement Path Later
- Contract versioning policy
- stronger auth hardening and route normalization
- richer retry/idempotency strategy
- deeper quality metrics per worker and full SLA/SLO definitions