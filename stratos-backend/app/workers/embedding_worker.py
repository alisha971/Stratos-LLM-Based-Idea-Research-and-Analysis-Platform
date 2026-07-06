from __future__ import annotations

from app.utils.redis_pub import publish_event
from app.workers.celery_app import celery_app


@celery_app.task(bind=True)
def run_embedding(self, report_id: str, chunk_ids: list[str]):
    """
    MVP no-op embedding worker.

    Section Writer already enqueues this task. Registering a no-op keeps the
    local pipeline from failing on an unknown Celery task until real embeddings
    are implemented.
    """
    publish_event(
        "embedding_skipped",
        {
            "report_id": report_id,
            "chunk_ids": chunk_ids,
            "reason": "Embedding worker is not implemented in MVP pipeline yet.",
        },
    )
