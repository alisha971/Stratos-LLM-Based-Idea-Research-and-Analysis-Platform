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
    READY_FOR_EXPORT = "READY_FOR_EXPORT"
 