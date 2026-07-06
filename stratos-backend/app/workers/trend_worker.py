"""
Trend Worker
- Fan-out across four free, no-key providers (HN, GDELT, Google News RSS, arXiv).
- Async parallel sibling of Research Worker; does NOT block section writing.
- Persists to Postgres `trends`/`trend_items` and mirrors to Astra `trend_items`.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from app.workers.celery_app import celery_app
from app.db.session import SessionLocal
from app.db import models
from app.services.trend_service import TrendService
from app.utils.redis_pub import publish_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def run_trend(self, report_id: str):
    """
    Trend Worker
    - Generates trend queries from clarified summary
    - Fans out across 4 free providers in parallel
    - Dedupes, caps, persists to Postgres + Astra
    - Emits scanning_trends, trend_ready, trend_failed events
    """
    db = SessionLocal()

    try:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        session = (
            db.query(models.Session).filter_by(id=report.session_id).first()
        )
        if not session or not session.clarified_summary:
            raise ValueError("Clarified summary missing")

        publish_event("scanning_trends", {"report_id": report_id})

        service = TrendService(db=db)
        queries = service.generate_queries(session.clarified_summary)
        logger.info("[TREND] Generated %d queries", len(queries))

        # --------------------------------------------------
        # PARALLEL PROVIDER FAN-OUT
        # --------------------------------------------------
        all_items: list[dict] = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for query in queries:
                futures.append(
                    executor.submit(
                        service._run_provider_safe,
                        service.fetch_hackernews,
                        query,
                        10,
                    )
                )
                futures.append(
                    executor.submit(
                        service._run_provider_safe,
                        service.fetch_gdelt,
                        query,
                        90,
                    )
                )
                futures.append(
                    executor.submit(
                        service._run_provider_safe,
                        service.fetch_google_news_rss,
                        query,
                        10,
                    )
                )
                futures.append(
                    executor.submit(
                        service._run_provider_safe,
                        service.fetch_arxiv,
                        query,
                        10,
                    )
                )

            for fut in as_completed(futures):
                try:
                    all_items.extend(fut.result() or [])
                except Exception:
                    logger.exception("[TREND] Provider future failed")

        logger.info("[TREND] Collected %d raw items pre-dedup", len(all_items))

        deduped = service.dedupe_items(all_items)
        capped = service.cap_items(deduped)
        logger.info(
            "[TREND] After dedup=%d cap=%d",
            len(deduped),
            len(capped),
        )

        # --------------------------------------------------
        # PERSISTENCE
        # --------------------------------------------------
        trend_id_by_category = service.persist_postgres(report_id, capped)
        service.persist_astra(report_id, capped, trend_id_by_category)

        by_category = _count_by_category(capped)

        publish_event(
            "trend_ready",
            {
                "report_id": report_id,
                "trend_count": len(capped),
                "by_category": by_category,
            },
        )

    except Exception as e:
        logger.exception("[TREND] Fatal error for report_id=%s", report_id)
        publish_event(
            "trend_failed",
            {"report_id": report_id, "error": str(e)},
        )
        raise

    finally:
        db.close()


def _count_by_category(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        category = item.get("category") or "news"
        counts[category] = counts.get(category, 0) + 1
    return counts
