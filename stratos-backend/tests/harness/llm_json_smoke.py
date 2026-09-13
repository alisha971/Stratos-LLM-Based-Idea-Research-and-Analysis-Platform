"""§3 valid-JSON-rate eval for the LLM JSON reliability plan
(`.claude/plans/llm_json_reliability_b7d24e08.plan.md`).

A script, not a pytest case -- it makes real Groq calls, same as this
directory's other harness scripts (test_citation_integrity.py,
fixture_loader.py) avoid live network dependence but this one deliberately
doesn't: it exists to pick/re-verify the heavy model.

For each of section_writer, verdict, competitor_profile, runs the real
prompt (built from a small hand-written canned context, via each service's
own `_build_prompt`/prompt string -- the exact code path production uses)
RUNS times against each candidate model on the `alisha` key (confirmed by
scripts/check_groq_models.py to have both MODEL_HEAVY and MODEL_LIGHT), and
reports valid_json_rate and mean completion tokens.

"Valid" means: the call didn't raise a Groq API error, parse_json_object
parsed it, AND (for section_writer/verdict, which have a real validator)
validate_*_draft accepted it against the same canned context.

Run:

    PYTHONPATH=. python tests/harness/llm_json_smoke.py

Keep this script for the next model swap -- re-run it before repointing
MODEL_HEAVY/MODEL_LIGHT at a different model id.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import groq

from app.config import settings  # noqa: F401 -- triggers load_dotenv() before client_groq reads env
from app.llm import client_groq
from app.llm.json_parse import parse_json_object
from app.llm.prompts import COMPETITOR_PROFILE_PROMPT
from app.llm.routing import MODEL_HEAVY, MODEL_LIGHT, TASK_MAX_TOKENS
from app.services.section_writer_service import SectionWriterService
from app.services.verdict_service import VerdictService

RUNS = 5
KEY_LABEL = "alisha"  # both MODEL_HEAVY and MODEL_LIGHT are confirmed live here

# Only models confirmed available on the routed key(s) by
# scripts/check_groq_models.py are exercised here. The other §3 candidates
# named in the plan (llama-3.3-70b-versatile, moonshotai/kimi-k2-instruct)
# were not available on either Groq account at the time of that check --
# add them back into this list if/when they become available.
CANDIDATE_MODELS = [MODEL_HEAVY, MODEL_LIGHT]


def _section_writer_case() -> tuple[str, Callable[[dict], None]]:
    service = SectionWriterService(db=None)
    context = {
        "section": {"title": "Competitor Landscape"},
        "report": {"idea_title": "AI meal-planning app for diabetics"},
        "outline_titles": [
            "Problem Context & Validation",
            "Competitor Landscape",
            "Market & Industry Trends",
        ],
        "citation_map": {
            "CIT-001": {
                "source_id": "source-1",
                "astra_evidence_id": "ev-1",
                "title": "Competitor A pricing page",
                "url": "https://competitor-a.example.com/pricing",
                "quote": "Competitor A offers onboarding templates and usage-based pricing.",
            },
            "CIT-002": {
                "source_id": "source-2",
                "astra_evidence_id": "ev-2",
                "title": "Competitor B feature comparison",
                "url": "https://competitor-b.example.com/features",
                "quote": "Competitor B differentiates on enterprise SSO and audit logs.",
            },
        },
        "unresolved_gaps": [],
        "source_mode": "web",
    }
    prompt = service._build_prompt(context)

    def validate(draft: dict) -> None:
        service.validate_section_draft(draft, context)

    return prompt, validate


def _verdict_case() -> tuple[str, Callable[[dict], None]]:
    service = VerdictService(db=None)
    context = {
        "report": {"idea_title": "AI meal-planning app for diabetics"},
        "sections": [
            {
                "title": "Problem Context & Validation",
                "text": "Diabetic patients struggle to plan meals within glycemic targets [CIT-001].",
            },
            {
                "title": "Competitor Landscape",
                "text": "Existing apps focus on calorie counting, not glycemic response [CIT-002].",
            },
        ],
        "marker_map": {
            "CIT-001": {
                "source_id": "s1",
                "stance": "supports",
                "domain": "example.com",
                "url": "https://a.example.com",
                "quote": "62% of surveyed diabetic patients report meal planning as a daily burden.",
            },
            "CIT-002": {
                "source_id": "s2",
                "stance": "challenges",
                "domain": "example.com",
                "url": "https://b.example.com",
                "quote": "Top 3 diabetes apps by installs all optimize for calorie count, not glycemic index.",
            },
        },
        "unresolved_gaps": [],
    }
    prompt = service._build_prompt(context)

    def validate(draft: dict) -> None:
        service.validate_verdict_draft(draft, context)

    return prompt, validate


def _competitor_profile_case() -> tuple[str, Callable[[dict], None]]:
    prompt = (
        COMPETITOR_PROFILE_PROMPT.replace("{{CANDIDATE_NAME}}", "MealMate")
        .replace(
            "{{HOMEPAGE_TEXT}}",
            "MealMate helps people with diabetes plan meals that keep blood sugar "
            "in range. Personalized plans, grocery lists, and a glucose-aware recipe "
            "database. Free 14-day trial.",
        )
        .replace(
            "{{PRICING_TEXT}}",
            "Free: basic meal plans. Premium ($9.99/mo): glucose tracking integration, "
            "grocery delivery partnerships, dietitian chat.",
        )
    )

    def validate(draft: dict) -> None:
        # No dedicated validator in competitor_service.py (profile() reads
        # fields defensively with .get()) -- a parsed JSON object is the bar.
        if not isinstance(draft, dict):
            raise ValueError("competitor_profile draft is not a JSON object")

    return prompt, validate


TASKS = {
    "section_writer": _section_writer_case,
    "verdict": _verdict_case,
    "competitor_profile": _competitor_profile_case,
}


def run_case(task: str, model: str) -> tuple[float, float]:
    prompt, validate = TASKS[task]()
    max_tokens = TASK_MAX_TOKENS.get(task, 768)
    client = client_groq._clients[KEY_LABEL]

    valid_count = 0
    completion_tokens: list[int] = []

    for _ in range(RUNS):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.2,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
        except groq.APIError as exc:
            print(f"    call failed: {exc}")
            continue

        usage = getattr(response, "usage", None)
        if usage is not None:
            completion_tokens.append(usage.completion_tokens)

        raw = response.choices[0].message.content.strip()
        try:
            draft = parse_json_object(raw, label=task)
            validate(draft)
            valid_count += 1
        except ValueError as exc:
            print(f"    invalid: {exc}")
        except (TypeError, AttributeError, KeyError) as exc:
            # A shape mismatch inside an otherwise-parseable JSON object
            # (e.g. a chunk that's a bare string instead of an object) --
            # still "invalid JSON output" for this eval's purposes, not a
            # harness bug.
            print(f"    invalid (malformed shape): {exc!r}")

    valid_rate = valid_count / RUNS
    mean_tokens = statistics.mean(completion_tokens) if completion_tokens else 0.0
    return valid_rate, mean_tokens


def main() -> int:
    print(f"Running {RUNS}x per (task, model) on key={KEY_LABEL}\n")
    results: dict[tuple[str, str], tuple[float, float]] = {}

    for task in TASKS:
        for model in CANDIDATE_MODELS:
            print(f"[{task}] model={model}")
            valid_rate, mean_tokens = run_case(task, model)
            results[(task, model)] = (valid_rate, mean_tokens)
            print(f"    valid_json_rate={valid_rate:.0%} mean_completion_tokens={mean_tokens:.0f}\n")

    print("Summary:")
    print(f"{'task':<20}{'model':<28}{'valid_json_rate':<18}{'mean_tokens'}")
    all_heavy_ok = True
    for (task, model), (valid_rate, mean_tokens) in results.items():
        print(f"{task:<20}{model:<28}{valid_rate:<18.0%}{mean_tokens:.0f}")
        if model == MODEL_HEAVY and valid_rate < 0.95:
            all_heavy_ok = False

    if not all_heavy_ok:
        print(f"\n{MODEL_HEAVY} did not clear 95% valid_json_rate on all tasks.")
        return 1

    print(f"\n{MODEL_HEAVY} clears >=95% valid_json_rate on all tasks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
