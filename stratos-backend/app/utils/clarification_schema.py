# app/utils/clarification_schema.py

from __future__ import annotations

import json
from typing import Any

IDEA_SCHEMA_FIELDS = [
    "project_domain",
    "target_persona",
    "core_problem",
    "current_workaround",
    "proposed_solution",
    "differentiation",
]

# Marker written into a schema field the user genuinely cannot answer. Stored as
# a dict (never prose) so it is machine-detectable and can never be mistaken for
# a real value by a downstream prompt.
UNKNOWN_KEY = "__unknown__"

# Reserved key kept alongside the schema fields inside the same JSONB column:
# every field that has actually been posed as a question in a prior turn.
# "unknown_detected" is only ever accepted for a field in this history -- the
# model cannot skip a field it never asked about.
ASKED_FIELDS_KEY = "_asked_fields"

# Reserved key: set once the user has actually described their idea. The first
# message may be a greeting, in which case session.idea_description holds "hi"
# provisionally until the first idea_content message backfills it. Also gates
# conversation completion -- pure chit-chat must never conclude into research.
IDEA_CAPTURED_KEY = "_idea_captured"

RESERVED_KEYS = {ASKED_FIELDS_KEY, IDEA_CAPTURED_KEY}

# Filled in when a template references a field that is itself still unknown, so
# a directive never reads "... in None serving None".
_FIELD_FALLBACKS = {
    "project_domain": "this domain",
    "target_persona": "the target users",
    "core_problem": "the core problem",
    "current_workaround": "existing workarounds",
    "proposed_solution": "the proposed solution",
    "differentiation": "differentiation",
}

# What to research when the user cannot answer. These must be actionable
# research tasks, not restatements of the gap.
UNKNOWN_DIRECTIVE_TEMPLATES = {
    "differentiation": (
        "Identify the unique selling points and positioning of existing "
        "competitors in {project_domain} serving {target_persona}. Map where "
        "those offerings fall short on {core_problem}, and synthesise concrete "
        "angles on which a new entrant could differentiate."
    ),
    "project_domain": (
        "Determine which domain or subfield {proposed_solution} belongs to, "
        "based on how comparable products position themselves."
    ),
    "target_persona": (
        "Identify which user segments experience {core_problem} most acutely, "
        "and which of them existing products in {project_domain} actually serve."
    ),
    "core_problem": (
        "Establish the most commonly reported problems that {target_persona} "
        "face in {project_domain}, and how severe each is."
    ),
    "current_workaround": (
        "Establish what {target_persona} do today to deal with {core_problem}, "
        "including manual workarounds and incumbent tools."
    ),
    "proposed_solution": (
        "Survey the approaches products in {project_domain} take to solve "
        "{core_problem}, and which have proven most effective."
    ),
}

GENERIC_UNKNOWN_DIRECTIVE = (
    "Research {field} for this idea, since it could not be established from "
    "the user's own knowledge."
)


def empty_schema() -> dict[str, Any]:
    return {field: None for field in IDEA_SCHEMA_FIELDS}


# ------------------------------------------------------------------
# Field state
# ------------------------------------------------------------------
def is_unknown(value: Any) -> bool:
    """True when the field was explicitly marked unresolvable by the user."""
    return isinstance(value, dict) and bool(value.get(UNKNOWN_KEY))


def is_filled(value: Any) -> bool:
    """True when the field carries a real user-supplied value."""
    if is_unknown(value):
        return False
    return value not in (None, "", [], {})


def is_resolved(value: Any) -> bool:
    """True when the field needs no further questioning.

    Either the user answered it, or they told us they cannot. Both end the
    questioning for that field — the second converts it into research.
    """
    return is_filled(value) or is_unknown(value)


def mark_unknown(field: str, directive: str) -> dict[str, Any]:
    return {UNKNOWN_KEY: True, "field": field, "directive": directive}


def unknown_directive(
    field: str,
    schema: dict[str, Any],
    llm_directives: Any = None,
) -> str:
    """Build the research task that replaces an unanswerable field.

    The template wins over anything the model proposed: left to itself the LLM
    restates the gap ("investigate potential unique features that could
    differentiate the app"), whereas the template names the actual research to
    perform. The model's own directives are still published separately in
    ``research_directives``, so nothing is lost.
    """
    template = UNKNOWN_DIRECTIVE_TEMPLATES.get(field)
    if not template:
        for directive in llm_directives or []:
            if isinstance(directive, str) and directive.strip():
                return directive.strip()
        return GENERIC_UNKNOWN_DIRECTIVE.format(field=field.replace("_", " "))

    values = {
        name: (
            str(schema.get(name))
            if is_filled(schema.get(name))
            else _FIELD_FALLBACKS[name]
        )
        for name in IDEA_SCHEMA_FIELDS
    }
    return template.format(**values)


def unresolved_fields(schema: dict[str, Any]) -> list[str]:
    """Schema fields still awaiting an answer."""
    return [
        field
        for field in IDEA_SCHEMA_FIELDS
        if not is_resolved(schema.get(field))
    ]


def unknown_fields(schema: dict[str, Any]) -> list[str]:
    return [field for field in IDEA_SCHEMA_FIELDS if is_unknown(schema.get(field))]


def confidence_score(schema: dict[str, Any]) -> float:
    """Fraction of schema fields that need no further questioning.

    Iterates IDEA_SCHEMA_FIELDS explicitly rather than schema.values(), so
    reserved keys stored in the same dict cannot inflate the score.
    """
    resolved = sum(
        1 for field in IDEA_SCHEMA_FIELDS if is_resolved(schema.get(field))
    )
    return round(resolved / len(IDEA_SCHEMA_FIELDS), 2)


# ------------------------------------------------------------------
# Boundary: everything below keeps markers out of downstream text
# ------------------------------------------------------------------
def serialize_for_downstream(
    schema: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Render the schema for storage in ``clarified_summary``.

    Unknown-marked fields become ``None`` and their directives are returned
    separately. This is the single choke point that stops marker dicts from
    reaching any prompt or the evidence ranker.
    """
    clean: dict[str, Any] = {}
    directives: list[str] = []

    for field in IDEA_SCHEMA_FIELDS:
        value = schema.get(field)
        if is_unknown(value):
            clean[field] = None
            directive = value.get("directive")
            if directive:
                directives.append(directive)
        else:
            clean[field] = value if is_filled(value) else None

    return clean, directives


def writer_view(clarified_summary: Any) -> dict[str, Any]:
    """Project ``clarified_summary`` down to what the section writer may see.

    Keeps established idea facts only. Research scaffolding
    (research_directives, knowledge_gaps, unknown_detected, confidence_score)
    and unresolved fields are dropped entirely — an omitted key cannot be
    quoted back into the report as if it were a finding.
    """
    data = clarified_summary
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return {}
    if not isinstance(data, dict):
        return {}

    raw_schema = data.get("final_schema")
    if isinstance(raw_schema, str):
        try:
            raw_schema = json.loads(raw_schema)
        except (ValueError, TypeError):
            raw_schema = None
    if not isinstance(raw_schema, dict):
        raw_schema = {}

    view: dict[str, Any] = {
        field: raw_schema.get(field)
        for field in IDEA_SCHEMA_FIELDS
        if is_filled(raw_schema.get(field))
    }

    constraints = data.get("hard_constraints")
    if isinstance(constraints, list) and constraints:
        view["hard_constraints"] = constraints

    return view
