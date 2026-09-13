"""Live Groq model-availability check for the LLM JSON reliability plan
(§3, `.claude/plans/llm_json_reliability_b7d24e08.plan.md`).

routing.py splits tasks between a heavy model (structured, long-output
tasks: section_writer/verdict/competitor_profile/outline) and a light model
(everything else), each pinned to one of the two Groq accounts
(`alisha`/`encril` -- see app/llm/client_groq.py). A model id that resolves
on one account can 404 on the other, so -- same discipline as
scripts/ensure_astra_collections.py -- verify against the live service
before committing the routing change, rather than trusting the id.

Run once before landing the §3 routing change:

    PYTHONPATH=. python scripts/check_groq_models.py

Exits non-zero if a model actually referenced by app.llm.routing.TASK_ROUTES
is not available on the key it's routed to.
"""

import sys

from app.config import settings  # noqa: F401 -- triggers load_dotenv() before client_groq reads env
from app.llm import client_groq
from app.llm.routing import MODEL_HEAVY, MODEL_LIGHT, TASK_ROUTES

# For reference only -- the other §3 candidates considered alongside
# MODEL_HEAVY, printed so a future re-tune doesn't have to re-derive this
# list. Not required to be available; only MODEL_HEAVY/MODEL_LIGHT are.
REFERENCE_CANDIDATES = [
    "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2-instruct",
]


def _available_models(key_label: str) -> set[str]:
    client = client_groq._clients[key_label]
    return {model.id for model in client.models.list().data}


def main() -> int:
    exit_code = 0
    availability: dict[str, set[str]] = {}

    for key_label in client_groq._clients:
        try:
            availability[key_label] = _available_models(key_label)
        except Exception as exc:  # network/auth error -- report, don't crash
            print(f"[{key_label}] FAILED to list models: {exc}")
            exit_code = 1
            continue

        print(f"\n[{key_label}] available models:")
        for candidate in [MODEL_HEAVY, MODEL_LIGHT, *REFERENCE_CANDIDATES]:
            mark = "OK" if candidate in availability[key_label] else "--"
            print(f"  [{mark}] {candidate}")

    # Cross-check every (key, model) pair TASK_ROUTES actually routes to.
    print("\nChecking routed pairs against live availability:")
    routed_pairs = {
        (key_label, model)
        for route in TASK_ROUTES.values()
        for key_label, model in route
    }
    for key_label, model in sorted(routed_pairs):
        models = availability.get(key_label)
        if models is None:
            continue  # already reported as a listing failure above
        if model in models:
            print(f"  OK   {key_label} -> {model}")
        else:
            print(f"  FAIL {key_label} -> {model} (NOT AVAILABLE)")
            exit_code = 1

    if exit_code:
        print(
            "\nOne or more routed models are not available on their key. "
            "Stop and re-pick from the printed list rather than editing "
            "around it -- do not substitute a model on your own judgement."
        )
    else:
        print("\nAll routed (key, model) pairs are available. Safe to proceed.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
