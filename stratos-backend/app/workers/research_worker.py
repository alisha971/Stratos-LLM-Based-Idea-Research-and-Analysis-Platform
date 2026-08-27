from sqlalchemy.orm import Session

from celery import group
from app.workers.celery_app import celery_app
from app.db.session import SessionLocal
from app.db import models
from app.services.research_service import ResearchService
from app.services.embedding_service import CONTENT_TYPE_WEB_CHUNK, EmbeddingService
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.utils.redis_pub import publish_event

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@celery_app.task(bind=True)
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
        embedding_service = EmbeddingService()

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
                            evidence_id = service.save_to_astra(
                                report_id=report_id,
                                source_id=source.id,
                                url=url,
                                text=snippet,
                                metadata={**result, "snippets": [snippet]},
                            )
                            # A news snippet is already atomic (Stage 2a) --
                            # one embedding, not chunked further.
                            embedding_service.save_chunk(
                                report_id=report_id,
                                content_type=CONTENT_TYPE_WEB_CHUNK,
                                text=snippet,
                                source_id=source.id,
                                evidence_id=evidence_id,
                                url=url,
                                domain=source.domain,
                            )

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

                    evidence_id = service.save_to_astra(
                        report_id=report_id,
                        source_id=source.id,
                        url=url,
                        text=full_text,
                        metadata={**result, "snippets": snippets},
                    )

                    # Stage 2c: vectorize on the ingestion path, so
                    # everything is ready by the time the Stage 1b join
                    # completes. Fail-soft -- an Astra/NVIDIA hiccup here
                    # degrades this source's ranking to lexical-only rather
                    # than failing the run (see EmbeddingService).
                    embedding_service.save_chunks(
                        report_id=report_id,
                        content_type=CONTENT_TYPE_WEB_CHUNK,
                        chunks=snippets,
                        source_id=source.id,
                        evidence_id=evidence_id,
                        url=url,
                        domain=source.domain,
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