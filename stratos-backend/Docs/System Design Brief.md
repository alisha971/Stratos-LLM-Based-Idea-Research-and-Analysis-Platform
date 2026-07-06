# System Design Brief

```mermaid
flowchart LR

    %% USERS
    User["Frontend User (Browser)"]

    %% API + AUTH
    APIGateway["API Gateway (FastAPI + SSE)"]
    AuthService["Auth Service (Google OAuth + JWT)"]

    %% CORE LOGIC
    Orchestrator["Orchestrator Service (State Machine)"]

    %% MESSAGING
    RedisBroker(("Redis Broker (Celery Tasks)"))
    RedisPub(("Redis PubSub (Events Stream)"))

    %% STORAGE
    Postgres[(Postgres DB\nSessions, Reports, Sections, Chunks, Citations, Chat)]
    AstraDB[(Astra DB\nVector Search + Evidence Store)]
    LocalFS[(Local Storage\nPDF/HTML Exports)]

    %% LLM
    LLM["LLM Provider"]

    %% WORKERS
    subgraph Workers["Celery Worker Microservices"]
        OutlineW["Outline Worker"]
        ResearchW["Research Worker"]
        TrendW["Trend Worker"]
        CompetitorW["Competitor Worker"]
        SectionW["Section Writer Worker\n(Inline Citations)"]
        EmbedW["Embedding Worker"]
        AssemblerW["Assembler Worker"]
        ExportW["Export Worker"]
    end

    %% FLOWS
    User --> APIGateway
    APIGateway --> AuthService
    AuthService --> APIGateway
    APIGateway --> Orchestrator

    %% ORCHESTRATOR → BROKER
    Orchestrator -->|Enqueue Jobs| RedisBroker

    %% BROKER → WORKERS
    RedisBroker --> OutlineW
    RedisBroker --> ResearchW
    RedisBroker --> TrendW
    RedisBroker --> CompetitorW
    RedisBroker --> SectionW
    RedisBroker --> EmbedW
    RedisBroker --> AssemblerW
    RedisBroker --> ExportW

    %% WORKERS → STORAGE
    OutlineW --> Postgres
    ResearchW --> Postgres
    ResearchW --> AstraDB
    TrendW --> Postgres
    TrendW --> AstraDB
    CompetitorW --> Postgres
    CompetitorW --> AstraDB
    SectionW --> Postgres
    SectionW --> AstraDB
    EmbedW --> AstraDB
    AssemblerW --> Postgres
    ExportW --> LocalFS
    ExportW --> Postgres

    %% WORKERS → LLM
    OutlineW --> LLM
    ResearchW --> LLM
    TrendW --> LLM
    CompetitorW --> LLM
    SectionW --> LLM
    EmbedW --> LLM
    AssemblerW --> LLM

    %% STREAMING EVENTS
    OutlineW -->|Events| RedisPub
    ResearchW -->|Events| RedisPub
    TrendW -->|Events| RedisPub
    CompetitorW -->|Events| RedisPub
    SectionW -->|Events| RedisPub
    EmbedW -->|Events| RedisPub
    AssemblerW -->|Events| RedisPub
    ExportW -->|Events| RedisPub

    RedisPub --> APIGateway
    APIGateway -->|SSE| User

    %% ORCHESTRATOR → DB
    Orchestrator --> Postgres
    Orchestrator --> AstraDB

```

## Eraser Sequence Diagram

```mermaid
title End-to-End AI Report Generation
autoNumber nested

// Actor definitions with icons and colors
User [icon: user, color: blue]
API Gateway [icon: globe, color: green]
Auth Service [icon: lock, color: green]
Orchestrator [icon: cpu, color: purple]
Redis Broker [icon: database, color: orange]
Outline Worker [icon: file-text, color: orange]
Research Worker [icon: search, color: orange]
Trend Worker [icon: trending-up, color: orange]
Competitor Worker [icon: users, color: orange]
Section Writer [icon: edit, color: orange]
Embedding Worker [icon: hash, color: orange]
Assembler Worker [icon: layers, color: orange]
Export Worker [icon: download, color: orange]
Postgres DB [icon: database, color: teal]
Astra DB [icon: database, color: teal]
LLM Provider [icon: cpu, color: purple]
"Redis Pub/Sub" [icon: message-circle, color: orange]
External API [icon: cloud, color: gray]
Renderer [icon: image, color: pink]
LocalFS [icon: hard-drive, color: pink]

// User login flow
User > API Gateway: Login with Google token
API Gateway > Auth Service: Validate token
Auth Service --> API Gateway: Valid
API Gateway --> User: Return JWT

// Session start
User > API Gateway: Start new idea session
API Gateway > Postgres DB: Create session and report rows
API Gateway > Orchestrator: Begin clarification

// Idea clarification
Orchestrator > LLM Provider: Generate clarifying questions
LLM Provider --> Orchestrator: Questions
Orchestrator --> "Redis Pub/Sub": clarification_questions

User > API Gateway: Answer clarifying questions
API Gateway > Orchestrator: Provide answers
Orchestrator > LLM Provider: Produce structured summary
LLM Provider --> Orchestrator: Summary
Orchestrator > Postgres DB: Save idea summary
Orchestrator --> "Redis Pub/Sub": ready_for_research

// User consent
User > API Gateway: Approve research
API Gateway > Orchestrator: Consent received

// Outline generation
Orchestrator > Redis Broker: enqueue outline_job
Redis Broker > Outline Worker: Execute
Outline Worker > LLM Provider: Generate outline
LLM Provider --> Outline Worker: Outline
Outline Worker > Postgres DB: Save sections
Outline Worker --> "Redis Pub/Sub": outline_ready

// Market research
Orchestrator > Redis Broker: enqueue research_job
Redis Broker > Research Worker: Execute
Research Worker --> "Redis Pub/Sub": searching_sources
Research Worker > External API: SERP search
External API --> Research Worker: Results
Research Worker > Astra DB: Save evidence
Research Worker > Postgres DB: Save metadata
Research Worker --> "Redis Pub/Sub": research_done

// Trend scan
Orchestrator > Redis Broker: enqueue trend_job
Redis Broker > Trend Worker: Execute
Trend Worker --> "Redis Pub/Sub": scanning_trends
Trend Worker > External API: News/Papers/Social
External API --> Trend Worker: Results
Trend Worker > Astra DB: Save evidence
Trend Worker > Postgres DB: Save metadata
Trend Worker --> "Redis Pub/Sub": trend_ready

// Competitor analysis
Orchestrator > Redis Broker: enqueue competitor_job
Redis Broker > Competitor Worker: Execute
Competitor Worker --> "Redis Pub/Sub": competitor_discovery
Competitor Worker > External API: Competitor search
External API --> Competitor Worker: Data
Competitor Worker > LLM Provider: Analyze competitors
LLM Provider --> Competitor Worker: Insights
Competitor Worker > Astra DB: Save evidence
Competitor Worker > Postgres DB: Save metadata
Competitor Worker --> "Redis Pub/Sub": competitor_done

// Section writing (streaming)
loop [label: For each section, icon: repeat] {
  Orchestrator > Astra DB: Load evidence bundle
  Orchestrator > Redis Broker: enqueue section_job
  Redis Broker > Section Writer: Execute
  Section Writer > LLM Provider: Stream chunks with inline citations
  LLM Provider --> Section Writer: Chunk stream
  Section Writer > Postgres DB: Save chunk
  Section Writer > Astra DB: Save provisional citations
  Section Writer --> "Redis Pub/Sub": section_chunk
  Section Writer > Redis Broker: enqueue embedding_job
}

// Embeddings
Redis Broker > Embedding Worker: Execute
Embedding Worker > Postgres DB: Load chunk
Embedding Worker > LLM Provider: Generate embedding
LLM Provider --> Embedding Worker: vector
Embedding Worker > Astra DB: Insert vector
Embedding Worker --> "Redis Pub/Sub": embedding_stored

// Export request
User > API Gateway: Export PDF/HTML
API Gateway > Redis Broker: enqueue assemble_job

// Assembler
Redis Broker > Assembler Worker: Execute
Assembler Worker > Postgres DB: Load sections, chunks, citations
Assembler Worker > LLM Provider: Polish and finalize report
LLM Provider --> Assembler Worker: Final structured report
Assembler Worker > Postgres DB: Save final_report_text
Assembler Worker > Redis Broker: enqueue export_job

// Export worker
Redis Broker > Export Worker: Execute
Export Worker > Postgres DB: Load final report text
Export Worker > Renderer: Render PDF/HTML
Renderer --> Export Worker: file
Export Worker > LocalFS: Save file
Export Worker > Postgres DB: Save export URL
Export Worker --> "Redis Pub/Sub": export_ready

// Deep dive (after report)
User > API Gateway: Ask deep-dive question
API Gateway > Orchestrator: deep_dive(report_id, question)
Orchestrator > LLM Provider: Query embedding
LLM Provider --> Orchestrator: vector
Orchestrator > Astra DB: Vector search
Astra DB --> Orchestrator: top-K chunks
Orchestrator > Postgres DB: Load citations and history
Orchestrator > LLM Provider: Grounded answer
LLM Provider --> Orchestrator: Answer
Orchestrator --> "Redis Pub/Sub": deep_dive_response
Orchestrator > Postgres DB: Save chat message
```

## Mermaid Sequence diagram

```mermaid
sequenceDiagram
    autonumber

    participant User as User
    participant API as API Gateway
    participant Auth as Auth Service
    participant Orch as Orchestrator
    participant Broker as Redis Broker
    participant OutlineW as Outline Worker
    participant ResearchW as Research Worker
    participant TrendW as Trend Worker
    participant CompetitorW as Competitor Worker
    participant SectionW as Section Writer
    participant EmbedW as Embedding Worker
    participant AssemblerW as Assembler Worker
    participant ExportW as Export Worker
    participant DB as Postgres DB
    participant Astra as Astra DB
    participant LLM as LLM Provider
    participant PubSub as Redis Pub/Sub

    %% LOGIN
    User ->> API: Login with Google Token
    API ->> Auth: Validate Token
    Auth -->> API: Valid
    API -->> User: Return JWT

    %% SESSION START
    User ->> API: Start new idea session
    API ->> DB: Create session + report rows
    API ->> Orch: Begin clarification

    %% IDEA CLARIFICATION
    Orch ->> LLM: Generate clarifying questions
    LLM -->> Orch: Questions
    Orch -->> PubSub: clarification_questions
    User ->> API: Answers clarifying questions
    API ->> Orch: Provide answers
    Orch ->> LLM: Produce structured summary
    LLM -->> Orch: Summary
    Orch ->> DB: Save idea summary
    Orch -->> PubSub: ready_for_research

    %% USER CONSENT
    User ->> API: Approve research
    API ->> Orch: Consent received

    %% OUTLINE GENERATION
    Orch ->> Broker: enqueue outline_job
    Broker ->> OutlineW: Execute
    OutlineW ->> LLM: Generate outline
    LLM -->> OutlineW: Outline
    OutlineW ->> DB: Save sections
    OutlineW -->> PubSub: outline_ready

    %% MARKET RESEARCH
    Orch ->> Broker: enqueue research_job
    Broker ->> ResearchW: Execute
    ResearchW -->> PubSub: searching_sources
    ResearchW ->> ExternalAPI: SERP search
    ExternalAPI -->> ResearchW: Results
    ResearchW ->> Astra: Save evidence
    ResearchW ->> DB: Save metadata
    ResearchW -->> PubSub: research_done

    %% TREND SCAN
    Orch ->> Broker: enqueue trend_job
    Broker ->> TrendW: Execute
    TrendW -->> PubSub: scanning_trends
    TrendW ->> ExternalAPI: News/Papers/Social
    ExternalAPI -->> TrendW: Results
    TrendW ->> Astra: Save evidence
    TrendW ->> DB: Save metadata
    TrendW -->> PubSub: trend_ready

    %% COMPETITOR ANALYSIS
    Orch ->> Broker: enqueue competitor_job
    Broker ->> CompetitorW: Execute
    CompetitorW -->> PubSub: competitor_discovery
    CompetitorW ->> ExternalAPI: Competitor search
    ExternalAPI -->> CompetitorW: Data
    CompetitorW ->> LLM: Analyze competitors
    LLM -->> CompetitorW: Insights
    CompetitorW ->> Astra: Save evidence
    CompetitorW ->> DB: Save metadata
    CompetitorW -->> PubSub: competitor_done

    %% SECTION WRITING (STREAMING)
    loop For each section
        Orch ->> Astra: Load evidence bundle
        Orch ->> Broker: enqueue section_job
        Broker ->> SectionW: Execute
        SectionW ->> LLM: Stream chunks with inline citations
        LLM -->> SectionW: Chunk stream
        SectionW ->> DB: Save chunk
        SectionW ->> Astra: Save provisional citations
        SectionW -->> PubSub: section_chunk
        SectionW ->> Broker: enqueue embedding_job
    end

    %% EMBEDDINGS
    Broker ->> EmbedW: Execute
    EmbedW ->> DB: Load chunk
    EmbedW ->> LLM: Generate embedding
    LLM -->> EmbedW: vector
    EmbedW ->> Astra: Insert vector
    EmbedW -->> PubSub: embedding_stored

    %% FINAL ANALYSIS ALREADY STREAMED — STOP HERE

    %% EXPORT REQUEST
    User ->> API: Export PDF/HTML
    API ->> Broker: enqueue assemble_job

    %% ASSEMBLER ONLY NOW RUNS
    Broker ->> AssemblerW: Execute
    AssemblerW ->> DB: Load sections + chunks + citations
    AssemblerW ->> LLM: Polish + finalize report
    LLM -->> AssemblerW: Final structured report
    AssemblerW ->> DB: Save final_report_text
    AssemblerW ->> Broker: enqueue export_job

    %% EXPORT WORKER
    Broker ->> ExportW: Execute
    ExportW ->> DB: Load final report text
    ExportW ->> Renderer: Render PDF/HTML
    Renderer -->> ExportW: file
    ExportW ->> LocalFS: Save file
    ExportW ->> DB: Save export URL
    ExportW -->> PubSub: export_ready

    %% DEEP DIVE (AFTER REPORT)
    User ->> API: Ask deep-dive question
    API ->> Orch: deep_dive(report_id, question)
    Orch ->> LLM: Query embedding
    LLM -->> Orch: vector
    Orch ->> Astra: Vector search
    Astra -->> Orch: top-K chunks
    Orch ->> DB: Load citations + history
    Orch ->> LLM: Grounded answer
    LLM -->> Orch: Answer
    Orch -->> PubSub: deep_dive_response
    Orch ->> DB: Save chat message

```