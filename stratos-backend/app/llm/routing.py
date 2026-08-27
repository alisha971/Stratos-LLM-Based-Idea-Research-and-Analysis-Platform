"""
Task -> ordered [(key_label, model), ...] routing.

Two Groq API keys/accounts share one model. Each task gets a primary key and
a fallback key; `section_writer` is by far the heaviest call site (~20 of the
~40-50 LLM calls in a single report run), so it gets a dedicated primary key
while every lighter task (clarification/outline/trend/research/competitor)
shares the other key as primary -- spreading load across both quotas instead
of piling everything onto one.
"""

MODEL = "openai/gpt-oss-20b"

DEFAULT_ROUTE = [("alisha", MODEL), ("encril", MODEL)]

TASK_ROUTES = {
    "outline": [("encril", MODEL), ("alisha", MODEL)],
    "clarification": [("encril", MODEL), ("alisha", MODEL)],
    "trend_query": [("encril", MODEL), ("alisha", MODEL)],
    "research_query": [("encril", MODEL), ("alisha", MODEL)],
    "competitor_terms": [("encril", MODEL), ("alisha", MODEL)],
    "competitor_relevance": [("encril", MODEL), ("alisha", MODEL)],
    "competitor_profile": [("encril", MODEL), ("alisha", MODEL)],
    "section_writer": [("alisha", MODEL), ("encril", MODEL)],
}
