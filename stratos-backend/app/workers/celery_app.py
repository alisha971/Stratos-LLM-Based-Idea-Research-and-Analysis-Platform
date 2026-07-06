from celery import Celery
from app.config import settings
import importlib
import logging

logger = logging.getLogger(__name__)

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
for module_name in (
    "app.workers.clarification_worker",
    "app.workers.outline_worker",
    "app.workers.research_worker",
    "app.workers.trend_worker",
    "app.workers.competitor_worker",
    "app.workers.section_worker",
    "app.workers.embedding_worker",
    "app.workers.assembler_worker",
    "app.workers.export_worker",
):
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        logger.info("Optional worker module not found: %s", module_name)