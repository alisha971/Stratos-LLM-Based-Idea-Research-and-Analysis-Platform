from enum import Enum

# Why Enum?

# Prevents typo bugs

# Makes transitions explicit

# Interviewers love this

class SessionState(str, Enum):
    CREATED = "CREATED"
    CLARIFYING = "CLARIFYING"
    AWAITING_CONSENT = "AWAITING_CONSENT"
    READY_FOR_RESEARCH = "READY_FOR_RESEARCH"
    OUTLINE_GENERATED = "OUTLINE_GENERATED"
    RESEARCH_RUNNING = "RESEARCH_RUNNING"
    WRITING_SECTIONS = "WRITING_SECTIONS"
    # Gap-closing plan Stage 4: sections are done, the verdict is being
    # synthesized before assembly. A verdict failure is non-fatal --
    # handle_stage_failed proceeds straight to run_assembler rather than
    # moving to FAILED, since the sections themselves are already complete.
    WRITING_VERDICT = "WRITING_VERDICT"
    READY_FOR_ASSEMBLY = "READY_FOR_ASSEMBLY"
    READY_FOR_EXPORT = "READY_FOR_EXPORT"
    EXPORTED = "EXPORTED"
    # Terminal, non-recoverable: reached when a pipeline stage publishes a
    # *_failed event this state machine treats as fatal (see
    # OrchestratorService.handle_stage_failed). Without this, a failed stage
    # left the session/report parked wherever they were -- indistinguishable
    # from "still running" to anyone watching.
    FAILED = "FAILED"
