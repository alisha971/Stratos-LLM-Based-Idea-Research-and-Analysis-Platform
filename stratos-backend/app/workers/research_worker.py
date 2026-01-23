from sqlalchemy.orm import Session

from celery import group
from app.workers.celery_app import celery_app
from app.db.session import SessionLocal
from app.db import models
from app.services.research_service import ResearchService
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.utils.redis_pub import publish_event

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def run_research(self, report_id: str):
    """
    Research Worker
    - Fetches external evidence
    - Stores raw evidence in Astra
    - Stores metadata in Postgres
    """
    
    db = SessionLocal()

    try:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")
        
        session = db.query(models.Session).filter_by(id=report.session_id).first()
        if not session or not session.clarified_summary:
            raise ValueError("Clarified summary missing")

        publish_event("searching_sources", {"report_id": report_id})

        service = ResearchService(db=db)

        queries = service.generate_queries(session.clarified_summary)
        logger.info(f"[RESEARCH] Generated {len(queries)} queries")
        
        # --------------------------------------------------
        # PARALLEL QUERY EXECUTION
        # --------------------------------------------------
        with ThreadPoolExecutor(max_workers=min(4, len(queries))) as executor:
            future_to_query = {
                executor.submit(service.search, query): query
                for query in queries
            }

            for future in as_completed(future_to_query):
                query = future_to_query[future]

                try:
                    results = future.result()
                except Exception:
                    logger.exception(
                        "[RESEARCH] SERP search failed for query=%s",
                        query,
                    )
                    continue

                logger.info(
                    "[RESEARCH] Processing %d results for query=%s",
                    len(results),
                    query,
                )

                # --------------------------------------------------
                # Result processing (SEQUENTIAL, DB-safe)
                # --------------------------------------------------
                for result in results:
                    url = result["url"]
                    source_type = result["type"]

                    if service.is_duplicate_url(report_id, url):
                        logger.debug(
                            "[RESEARCH] Duplicate URL skipped: %s",
                            url,
                        )
                        continue

                    # ---------------------------
                    # NEWS → snippet only
                    # ---------------------------
                    if source_type == "news":
                        source = service.create_source(report_id, result)

                        snippet = result.get("snippet")
                        if snippet:
                            service.save_evidence(source.id, [snippet])

                        continue

                    # ---------------------------
                    # PATENT → metadata only
                    # ---------------------------
                    if source_type == "patent":
                        service.create_source(report_id, result)
                        continue

                    # ---------------------------
                    # WEB → scrape required
                    # ---------------------------
                    snippets, full_text = service.scrape_and_extract(url)

                    logger.debug(
                        "[RESEARCH] Extracted %d snippets from %s",
                        len(snippets),
                        url,
                    )

                    if not snippets:
                        continue

                    source = service.create_source(report_id, result)
                    service.save_evidence(source.id, snippets)

                    service.save_to_astra(
                        report_id=report_id,
                        source_id=source.id,
                        url=url,
                        text=full_text,
                        metadata=result,
                    )

        publish_event("research_done", {"report_id": report_id})

    except Exception as e:
        publish_event(
            "research_failed",
            {"report_id": report_id, "error": str(e)},
        )
        raise

    finally:
        db.close()