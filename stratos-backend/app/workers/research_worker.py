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

# Provenance prior (Stage 3e step 1): a source found by the counter pass
# starts "challenges" (the pass exists specifically to find disconfirming
# evidence); a main-pass or directive-seed source starts "neutral", since a
# topic-descriptive query says nothing about which way its results lean.
# Refined later by classify_stance() -- an actual LLM read of the source
# relative to this idea, not just which query found it.
STANCE_PRIOR_MAIN = "neutral"
STANCE_PRIOR_COUNTER = "challenges"


@celery_app.task(bind=True)
def run_research(self, report_id: str):
    """
    Research Worker
    - Fetches external evidence (main pass: confirmatory; counter pass:
      deliberately adversarial -- Stage 3a)
    - Stores raw evidence in Astra, vectorized on the ingestion path
      (Stage 2c)
    - Stores metadata + a stance provenance prior in Postgres (Stage 3e),
      refined by a batched LLM classification once ingestion completes
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
        idea_description = session.idea_description or ""

        # --------------------------------------------------
        # QUERY GENERATION: main + counter pass concurrently (Stage 3a).
        # Independent LLM calls on different primary Groq keys
        # (research_query / research_query_counter in routing.py), so
        # running them concurrently roughly halves this stage's wall time
        # instead of just spreading load across keys that fire serially.
        # --------------------------------------------------
        with ThreadPoolExecutor(max_workers=2) as query_executor:
            main_future = query_executor.submit(
                service.generate_queries,
                session.clarified_summary,
                idea_description=idea_description,
                report_id=report_id,
            )
            counter_future = query_executor.submit(
                service.generate_counter_queries,
                session.clarified_summary,
                idea_description=idea_description,
                report_id=report_id,
            )
            main_queries = main_future.result()
            counter_queries = counter_future.result()

        # Stage 3c: research directives (fields the user couldn't answer)
        # join the main pass -- they're about filling knowledge gaps, not
        # deliberately adversarial framing, so a directive-seeded source
        # gets the same "neutral" prior as a regular main-pass source.
        directive_seeds = service.seed_queries_from_directives(session.clarified_summary)

        # Tag every query with which pass produced it, so results inherit
        # the right stance prior below. Dedup across the three sources
        # (a directive seed could coincide with an LLM-generated query).
        queries_with_pass: list[tuple[str, str]] = []
        seen_queries: set[str] = set()
        for query in [*main_queries, *directive_seeds]:
            if query not in seen_queries:
                queries_with_pass.append((query, STANCE_PRIOR_MAIN))
                seen_queries.add(query)
        for query in counter_queries:
            if query not in seen_queries:
                queries_with_pass.append((query, STANCE_PRIOR_COUNTER))
                seen_queries.add(query)

        logger.info(
            "[RESEARCH] Generated %d queries (%d main, %d directive seeds, %d counter)",
            len(queries_with_pass),
            len(main_queries),
            len(directive_seeds),
            len(counter_queries),
        )

        # --------------------------------------------------
        # PARALLEL QUERY EXECUTION
        # --------------------------------------------------
        newly_created_source_ids: list[str] = []

        # 2026-09-14 remediation Phase 4.2: news/patent results need no
        # scrape (their content is already in the SERP result) and are
        # handled immediately below, DB-safe on the main thread as
        # before. Web results need a real fetch -- collected here instead
        # of scraped inline, so ALL of them (across every query, not just
        # one query's sub-batch) can go through ONE shared scrape pool
        # below rather than nesting a fresh pool per query.
        web_results_to_scrape: list[tuple[dict, str]] = []

        with ThreadPoolExecutor(max_workers=min(4, len(queries_with_pass) or 1)) as executor:
            future_to_query = {
                executor.submit(service.search, query): (query, stance_prior)
                for query, stance_prior in queries_with_pass
            }

            for future in as_completed(future_to_query):
                query, stance_prior = future_to_query[future]

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
                # Result triage (SEQUENTIAL, DB-safe): is_duplicate_url
                # and create_source both touch the SQLAlchemy Session,
                # which is not thread-safe -- this loop stays on the main
                # thread. Only the scrape itself (network I/O, no DB) is
                # deferred to the shared pool below.
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
                        source = service.create_source(report_id, result, stance=stance_prior)
                        newly_created_source_ids.append(source.id)

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
                                stance=stance_prior,
                            )

                        continue

                    # ---------------------------
                    # PATENT → metadata only
                    # ---------------------------
                    if source_type == "patent":
                        source = service.create_source(report_id, result, stance=stance_prior)
                        newly_created_source_ids.append(source.id)
                        continue

                    # ---------------------------
                    # WEB → deferred to the shared scrape pool below
                    # ---------------------------
                    web_results_to_scrape.append((result, stance_prior))

        # --------------------------------------------------
        # SHARED SCRAPE POOL (Phase 4.2): scrape_and_extract is pure
        # network I/O + HTML clean + chunk -- no DB access -- so every
        # web result collected above (across every query) is fetched
        # concurrently here, bounded at 4 in flight (matches the SERP
        # pool's own bound; safe_fetch's module-level Session and
        # thread-local IP pinning already support concurrent callers --
        # see safe_fetch.py's own docstring on this).
        # --------------------------------------------------
        logger.info(
            "[RESEARCH] Scraping %d web results across all queries",
            len(web_results_to_scrape),
        )
        with ThreadPoolExecutor(
            max_workers=min(4, len(web_results_to_scrape) or 1)
        ) as scrape_executor:
            scrape_future_to_entry = {
                scrape_executor.submit(
                    service.scrape_and_extract, result["url"], report_id=report_id
                ): (result, stance_prior)
                for result, stance_prior in web_results_to_scrape
            }

            # --------------------------------------------------
            # Result processing (SEQUENTIAL, DB-safe): as each scrape
            # completes, its Postgres/Astra/embedding writes still happen
            # one at a time on the main thread -- only the fetch itself
            # ran concurrently above.
            # --------------------------------------------------
            for scrape_future in as_completed(scrape_future_to_entry):
                result, stance_prior = scrape_future_to_entry[scrape_future]
                url = result["url"]

                try:
                    snippets, full_text = scrape_future.result()
                except Exception:
                    logger.exception("[RESEARCH] Scrape failed for url=%s", url)
                    continue

                logger.debug(
                    "[RESEARCH] Extracted %d snippets from %s",
                    len(snippets),
                    url,
                )

                if not snippets:
                    continue

                source = service.create_source(report_id, result, stance=stance_prior)
                newly_created_source_ids.append(source.id)
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
                    stance=stance_prior,
                )

        # Stage 3e step 2: refine every provenance prior set above with an
        # actual LLM read of each source against this specific idea.
        # Fail-soft (see ResearchService.classify_stance) -- never blocks
        # research_done on a classification hiccup.
        service.classify_stance(
            report_id=report_id,
            clarified_summary=session.clarified_summary,
            source_ids=newly_created_source_ids,
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
