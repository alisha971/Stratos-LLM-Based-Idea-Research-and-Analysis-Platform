"""
Competitor Worker
- Discovers candidate competitors from Product Hunt + Hacker News "Show HN".
- Async parallel sibling of Trend Worker; does NOT block section writing.
- Verifies every candidate via a real SSRF-guarded homepage fetch before
  profiling or persisting it — never trust a name the LLM merely recalls.
- Persists to Postgres (Source + Competitor + CompetitorFeature) and mirrors
  to Astra `competitor_insights`.
- Fail-soft throughout: the pipeline must still reach EXPORTED even if this
  worker finds nothing or errors out entirely.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from app.config import settings
from app.workers.celery_app import celery_app
from app.db.session import SessionLocal
from app.db import models
from app.services.competitor_service import (
    VERIFICATION_POOL_MULTIPLIER,
    CompetitorService,
)
from app.utils.redis_pub import publish_event

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@celery_app.task(bind=True)
def run_competitor(self, report_id: str):
    """
    Competitor Worker
    - Generates category keywords from clarified summary
    - Fans out across Product Hunt + Show HN in parallel, per keyword
    - Relevance-filters, verifies (real homepage fetch), profiles, persists
    - Emits scanning_competitors, competitor_ready, competitor_failed events
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

        publish_event("scanning_competitors", {"report_id": report_id})

        service = CompetitorService(db=db)
        terms = service.derive_search_terms(session.clarified_summary)
        keywords = terms["keywords"]
        logger.info("[COMPETITOR] Derived keywords: %s", keywords)

        # --------------------------------------------------
        # DISCOVERY FAN-OUT (Product Hunt + Show HN, per keyword)
        # --------------------------------------------------
        raw_candidates: list[dict] = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for keyword in keywords:
                futures.append(
                    executor.submit(
                        service._run_provider_safe,
                        service.fetch_product_hunt,
                        keyword,
                    )
                )
                futures.append(
                    executor.submit(
                        service._run_provider_safe,
                        service.fetch_show_hn,
                        keyword,
                    )
                )

            for fut in as_completed(futures):
                try:
                    raw_candidates.extend(fut.result() or [])
                except Exception:
                    logger.exception("[COMPETITOR] Discovery future failed")

        logger.info(
            "[COMPETITOR] Collected %d raw candidates pre-dedup",
            len(raw_candidates),
        )

        candidates = service.dedupe_candidates(raw_candidates)
        logger.info(
            "[COMPETITOR] %d candidates after pre-fetch dedupe",
            len(candidates),
        )

        # --------------------------------------------------
        # RELEVANCE FILTER (LLM, cheap metadata only)
        # --------------------------------------------------
        pool_size = settings.COMPETITOR_MAX * VERIFICATION_POOL_MULTIPLIER
        ranked = service.filter_relevant(
            session.clarified_summary,
            candidates,
            pool_size,
        )
        logger.info(
            "[COMPETITOR] %d candidates selected for verification",
            len(ranked),
        )

        # --------------------------------------------------
        # VERIFICATION (parallel, SSRF-guarded homepage fetches)
        # This is the anti-hallucination wall: a candidate that fails here
        # is dropped, never profiled or persisted.
        # --------------------------------------------------
        verified: list[dict] = []
        dropped = 0
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_to_candidate = {
                executor.submit(service.verify, candidate): candidate
                for candidate in ranked
            }
            for fut in as_completed(future_to_candidate):
                candidate = future_to_candidate[fut]
                try:
                    resolved_url, homepage_text, pricing_text = fut.result()
                except Exception:
                    logger.exception(
                        "[COMPETITOR] Verification future failed for %s",
                        candidate.get("name"),
                    )
                    resolved_url = None
                    homepage_text = None
                    pricing_text = None

                if not resolved_url or not homepage_text:
                    dropped += 1
                    continue

                verified.append(
                    {
                        **candidate,
                        "resolved_url": resolved_url,
                        "homepage_text": homepage_text,
                        "pricing_text": pricing_text,
                    }
                )

        logger.info(
            "[COMPETITOR] %d verified, %d dropped at verification",
            len(verified),
            dropped,
        )

        deduped = service.dedupe_by_domain(verified)
        capped = deduped[: settings.COMPETITOR_MAX]

        # --------------------------------------------------
        # PROFILING (one LLM call per verified competitor)
        # --------------------------------------------------
        profiled = [
            {**entry, "profile": service.profile(entry, entry["homepage_text"], entry.get("pricing_text"))}
            for entry in capped
        ]

        # --------------------------------------------------
        # PERSISTENCE
        # --------------------------------------------------
        persisted = service.persist_postgres(report_id, profiled)
        service.persist_astra(report_id, persisted)

        publish_event(
            "competitor_ready",
            {
                "report_id": report_id,
                "competitors_count": len(persisted),
                "verified_count": len(verified),
                "dropped_count": dropped,
            },
        )

    except Exception as e:
        logger.exception("[COMPETITOR] Fatal error for report_id=%s", report_id)
        publish_event(
            "competitor_failed",
            {"report_id": report_id, "error": str(e)},
        )
        raise

    finally:
        db.close()
