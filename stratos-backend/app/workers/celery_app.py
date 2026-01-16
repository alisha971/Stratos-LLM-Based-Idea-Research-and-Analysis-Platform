from celery import Celery
from app.config import settings

celery_app = Celery(
    "stratos",
    broker=settings.REDIS_BROKER_URL,
    backend=settings.REDIS_BROKER_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# 🔥 FORCE TASK REGISTRATION
import app.workers.clarification_worker
import app.workers.outline_worker

import app.workers.research_worker
import app.workers.trend_worker
import app.workers.competitor_worker
import app.workers.section_worker
import app.workers.embedding_worker
import app.workers.assembler_worker
import app.workers.export_worker