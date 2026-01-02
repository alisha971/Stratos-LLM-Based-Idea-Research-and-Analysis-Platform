from app.workers.celery_app import celery_app
from app.llm.client import generate_text
from app.llm.prompts import CLARIFICATION_PROMPT
from app.utils.redis_pub import publish_event


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def run_clarification(self, session_id: str, idea: str):
    publish_event("clarification_started", {"session_id": session_id})

    output = generate_text(
        system_prompt=CLARIFICATION_PROMPT,
        user_prompt=idea,
    )

    questions = [
        q.strip()
        for q in output.split("\n")
        if q.strip()
    ]

    publish_event(
        "clarification_questions",
        {
            "session_id": session_id,
            "questions": questions,
        },
    )

    return questions
