"""
Task -> ordered [(key_label, model), ...] routing.

Two Groq API keys/accounts, two models. The model is picked by TASK WEIGHT,
the key by LOAD SHAPING -- the two vary independently:

- Heavy / structured tasks (section_writer, verdict, competitor_profile,
  outline -- long, multi-field JSON) route to MODEL_HEAVY
  (openai/gpt-oss-120b), which follows the response_format={"json_object"}
  constraint far more reliably at this output length than the 20B variant.
  Their primary key is `alisha`, concentrating heavy work on one quota.
- Light / high-volume tasks (research_query, trend_query,
  stance_classification, competitor_terms, competitor_relevance,
  clarification) route to MODEL_LIGHT (openai/gpt-oss-20b) -- cheap, fast,
  and small-JSON is where it's reliable. Their primary key is `encril`.
- A heavy task's FALLBACK key is `encril` at MODEL_LIGHT, not MODEL_HEAVY on
  the same key twice: degraded-but-alive (a 20B retry) beats failing
  outright when the 120B key is rate-limited. The worker-level repair retry
  (see app/workers/section_worker.py, verdict_worker.py) is the backstop if
  that 20B fallback itself produces bad JSON.
- Exception: research_query_counter keeps `alisha` as its PRIMARY KEY (so
  the counter pass runs concurrently with the main research_query pass on
  the other key, per the gap-closing plan Stage 3a) but still uses
  MODEL_LIGHT -- do not "fix" this to `encril`, it would put both research
  passes on one quota.

Before changing either model id, run scripts/check_groq_models.py to verify
it actually resolves on the key(s) that will route to it -- see
`.claude/plans/llm_json_reliability_b7d24e08.plan.md` §3.
"""

MODEL_HEAVY = "openai/gpt-oss-120b"   # structured, long-output tasks
MODEL_LIGHT = "openai/gpt-oss-20b"    # small-JSON, high-volume tasks

DEFAULT_ROUTE = [("alisha", MODEL_LIGHT), ("encril", MODEL_LIGHT)]

TASK_ROUTES = {
    "outline": [("alisha", MODEL_HEAVY), ("encril", MODEL_LIGHT)],
    "clarification": [("encril", MODEL_LIGHT), ("alisha", MODEL_LIGHT)],
    "trend_query": [("encril", MODEL_LIGHT), ("alisha", MODEL_LIGHT)],
    "research_query": [("encril", MODEL_LIGHT), ("alisha", MODEL_LIGHT)],
    # Counter pass (gap-closing plan Stage 3a) gets the OTHER primary key
    # from the main research_query pass, so the two run concurrently
    # without both hammering the same quota. Note the fallback chain still
    # crosses over -- under real pressure both converge on whichever key
    # is alive; this is load-shaping, not isolation. Stays MODEL_LIGHT --
    # this is a high-volume task, not a heavy/structured one.
    "research_query_counter": [("alisha", MODEL_LIGHT), ("encril", MODEL_LIGHT)],
    "stance_classification": [("encril", MODEL_LIGHT), ("alisha", MODEL_LIGHT)],
    "competitor_terms": [("encril", MODEL_LIGHT), ("alisha", MODEL_LIGHT)],
    "competitor_relevance": [("encril", MODEL_LIGHT), ("alisha", MODEL_LIGHT)],
    "competitor_profile": [("alisha", MODEL_HEAVY), ("encril", MODEL_LIGHT)],
    "section_writer": [("alisha", MODEL_HEAVY), ("encril", MODEL_LIGHT)],
    "verdict": [("alisha", MODEL_HEAVY), ("encril", MODEL_LIGHT)],
}

# 4096 is within the completion ceiling of every Groq model currently routed
# here. Re-check this when swapping MODEL_HEAVY/MODEL_LIGHT.
DEFAULT_MAX_TOKENS = 768
TASK_MAX_TOKENS = {
    "section_writer": 4096,
    "verdict": 2048,
    "competitor_profile": 1536,
    "outline": 1536,
    "clarification": 1280,
}
