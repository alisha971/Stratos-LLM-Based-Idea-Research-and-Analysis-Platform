"""
Backward-compatible shim (2026-09-14 remediation Phase 3.3.a).

The real implementation moved to app/llm/providers/groq_provider.py (the
new canonical location for every provider adapter). This module re-exports
`generate_chat` and `_clients` UNCHANGED so existing import sites
(app/llm/client.py's `_groq_call` seam) and tests/test_client_groq.py,
which patches `client_groq._clients` in place, keep working exactly as
before without modification. `_clients` below is the SAME dict object as
`groq_provider._clients` (not a copy) -- `patch.dict` mutates a dict's
contents in place, so patching it through either name affects both.

Prefer importing from app.llm.providers.groq_provider in new code; this
module exists only for backward compatibility.
"""

from __future__ import annotations

from app.llm.providers.groq_provider import _clients, complete, generate_chat

__all__ = ["generate_chat", "complete", "_clients"]
