# app/utils/clarification_schema.py

IDEA_SCHEMA_FIELDS = [
    "project_domain",
    "target_persona",
    "core_problem",
    "current_workaround",
    "proposed_solution",
    "differentiation",
]


def empty_schema():
    return {field: None for field in IDEA_SCHEMA_FIELDS}


def confidence_score(schema: dict) -> float:
    score = 0.0

    if schema.get("target_persona"):
        score += 0.2
    if schema.get("core_problem"):
        score += 0.2
    if schema.get("proposed_solution"):
        score += 0.2
    if schema.get("differentiation"):
        score += 0.25
    if schema.get("current_workaround"):
        score += 0.15

    return min(score, 1.0)
