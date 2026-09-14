# TODO: Integrate SERP API (SerpAPI / Bing / Brave)
# TODO: Domain filtering (wikipedia, blogs, product pages)
# TODO: Duplicate URL detection
# TODO: Rate limiting
# TODO: Timeout handling

# app/services/research_service.py

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from serpapi import GoogleSearch
from typing import List, Dict
from datetime import datetime

from app.db import models
from app.config import settings
from app.utils.safe_fetch import BlockedRequestError, safe_get
from app.utils.text_cleaner import clean_html
from app.utils.chunking import chunk_text
from app.utils.clarification_schema import research_directives
from app.utils.redis_pub import publish_event
from app.utils.degradation import record_degradation
from app.llm.client import generate_chat
from app.llm.json_parse import parse_json_object
from app.llm.repair import generate_with_repair
from app.llm.prompts import (
    COUNTER_RESEARCH_QUERY_PROMPT,
    RESEARCH_QUERY_PROMPT,
    STANCE_CLASSIFICATION_PROMPT,
)
from app.services.astra_evidence_repository import AstraEvidenceRepository
import json

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAIN_PASS_QUERY_COUNT = 5
# Capped below the main pass (gap-closing plan Stage 3a): a same-size
# counter pass would roughly double SerpAPI usage (there is one shared
# SERP_API_KEY) for a handful of genuinely disconfirming sources, not
# exhaustive coverage.
COUNTER_PASS_QUERY_COUNT = 3
MAX_DIRECTIVE_SEEDS = 2
STANCE_BATCH_SIZE = 10
VALID_STANCES = {"supports", "challenges", "neutral"}

# Fix-audit Part 0 Rule 1: the stance-classification prompt emits one JSON
# object per source in the batch, but the call used to run on a fixed
# per-task token budget (DEFAULT_MAX_TOKENS=768) that didn't scale with
# STANCE_BATCH_SIZE. A full batch of 10 -- especially with the gpt-oss
# hidden reasoning channel eating into the same budget -- could overrun it,
# Groq's json_object validator would see truncated JSON, and the batch fell
# straight to its fallback as a routine, not exceptional, event. The
# per-source allowance below is deliberately generous (id + stance word +
# one short rationale sentence + JSON punctuation is normally <40 tokens).
STANCE_TOKENS_BASE = 120
# Raised 90 -> 140 (2026-09-14 remediation, audit §7.4): the live
# verification run truncated on a 3-source batch, well under the 10-source
# STANCE_BATCH_SIZE cap -- proving the failure isn't purely a function of
# batch size and there's real per-call variance (plausibly the model's
# hidden reasoning channel consuming a variable share of the budget).
# Widening the per-source allowance reduces, though does not guarantee
# eliminating, this risk.
STANCE_TOKENS_PER_SOURCE = 140

# Astra caps any *indexed* string field at 8000 bytes, and the `evidence`
# collection indexes every field (no deny-list at creation). `raw_text` is
# the whole cleaned page -- routinely 10-40 KB -- so writing it uncapped
# fails the entire document with SHRED_DOC_LIMIT_VIOLATION and the archive
# silently keeps only short pages. Cap well under the limit, measured in
# UTF-8 bytes (not characters, which is what a plain slice counts). The
# full page is still recoverable chunk-by-chunk from `embeddings`.
EVIDENCE_RAW_TEXT_MAX_BYTES = 7800


def _truncate_utf8_bytes(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # errors="ignore" drops a trailing byte sequence left dangling by the
    # cut, so the result is always valid UTF-8.
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


class ResearchService:
    def __init__(self, db: Session):
        self.db = db
        self.astra_repository = AstraEvidenceRepository()

    # --------------------------------------------------
    # Query generation
    # --------------------------------------------------
    def generate_queries(
        self,
        clarified_summary: str,
        *,
        idea_description: str = "",
        report_id: str | None = None,
    ) -> list[str]:
        """Main pass: confirmatory queries (existing solutions, competitors,
        market, trends, pain points). Fallback to deterministic queries on
        any LLM/parsing failure -- see _fallback_queries."""
        return self._generate_queries(
            clarified_summary,
            prompt_template=RESEARCH_QUERY_PROMPT,
            task="research_query",
            max_queries=MAIN_PASS_QUERY_COUNT,
            idea_description=idea_description,
            report_id=report_id,
        )

    def generate_counter_queries(
        self,
        clarified_summary: str,
        *,
        idea_description: str = "",
        report_id: str | None = None,
    ) -> list[str]:
        """Counter pass (Stage 3a): queries deliberately framed to surface
        DISCONFIRMING evidence -- failed attempts, incumbent moats,
        regulatory load, negative reviews, market-size skepticism. Run
        this alongside generate_queries(), not instead of it; see
        research_worker.py for the concurrent dispatch and the
        research_query_counter routing key."""
        return self._generate_queries(
            clarified_summary,
            prompt_template=COUNTER_RESEARCH_QUERY_PROMPT,
            task="research_query_counter",
            max_queries=COUNTER_PASS_QUERY_COUNT,
            idea_description=idea_description,
            report_id=report_id,
        )

    def seed_queries_from_directives(self, clarified_summary: str) -> list[str]:
        """Stage 3c: research directives (schema fields the user couldn't
        answer, converted to research questions by the clarification
        worker -- see unknown_directive) become query SEEDS up front, not
        only a report-time gap list. Deterministic, no LLM call, cannot
        fail -- distinct from _fallback_queries below, which only fires
        when query GENERATION itself broke."""
        directives = research_directives(clarified_summary)
        seeds = [d for d in directives if 3 <= len(d.split()) <= 20]
        return seeds[:MAX_DIRECTIVE_SEEDS]

    def _generate_queries(
        self,
        clarified_summary: str,
        *,
        prompt_template: str,
        task: str,
        max_queries: int,
        idea_description: str,
        report_id: str | None,
    ) -> list[str]:
        if not clarified_summary:
            raise ValueError("Clarified summary missing")

        prompt = prompt_template.replace(
            "{{CLARIFIED_SUMMARY}}",
            clarified_summary,
        )

        try:
            raw = generate_chat(
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3,
                task=task,
            )

            data = json.loads(raw)
            queries = data.get("queries")

            if not isinstance(queries, list) or not queries:
                raise ValueError("Invalid queries format")

            cleaned = []
            for q in queries:
                if isinstance(q, str) and 3 <= len(q.split()) <= 12:
                    cleaned.append(q.strip())

            if not cleaned:
                raise ValueError("No valid queries")

            logger.info("[RESEARCH] Generated %d queries task=%s", len(cleaned), task)

            return cleaned[:max_queries]

        except Exception:
            # The idea description was fine -- this is a MACHINERY failure
            # (LLM call, JSON parsing, word-count filter), not a sign the
            # idea can't be researched. Degrade to a fallback that's still
            # about the right subject, and say so, rather than silently
            # handing SerpAPI three generic strings with no relation to
            # the idea (see stratos-launch-plan Stage 3b).
            logger.warning(
                "[RESEARCH] Query generation failed task=%s; using templated fallback",
                task,
                exc_info=True,
            )
            if report_id:
                publish_event(
                    "research_degraded",
                    {"report_id": report_id, "stage": "query_generation", "task": task},
                )
            return self._fallback_queries(idea_description, max_queries)

    def _fallback_queries(self, idea_description: str, max_queries: int) -> list[str]:
        idea = (idea_description or "").strip()
        if not idea:
            # No idea text available at all to template against -- last
            # resort. Still flagged via research_degraded above, unlike
            # the old fallback, which was both generic AND silent.
            templates = ["existing solutions", "competitor tools", "market overview"]
        else:
            templates = [
                f"{idea} competitors",
                f"{idea} market size",
                f"{idea} alternatives",
                f"{idea} pricing",
                f"{idea} reviews",
            ]
        return templates[:max_queries]

    # --------------------------------------------------
    # Stance classification (Stage 3e step 2)
    #
    # Step 1, the provenance PRIOR ("challenges" for counter-pass results,
    # "neutral" for main-pass), is set inline at ingestion in
    # run_research -- free, but only a prior, not proof. This is step 2:
    # the actual mechanism, an LLM reading each source's quote relative to
    # THIS idea and refining that prior. Batched (~10/call) against
    # Postgres Source rows created by THIS run only (source_ids is the
    # list run_research built during its own ingestion loop) -- never a
    # blind re-query of the report's sources, since research/trend/
    # competitor workers run concurrently on the same report_id (Stage 1b)
    # and competitor sources are a different type entirely.
    # --------------------------------------------------
    def classify_stance(
        self,
        report_id: str,
        clarified_summary: str,
        source_ids: list[str],
    ) -> None:
        """
        2026-09-14 remediation Phase 4.6: classify_stance gates
        research_done, which gates the research/trend/competitor join,
        which gates all 7 sections -- so its own batches (STANCE_BATCH_SIZE
        source_ids each) used to run one after another even though the
        actual LLM calls have no dependency on each other. Split into
        three phases: (1) prepare every batch's prompt SEQUENTIALLY (DB
        reads -- Source/SourceEvidence queries -- stay on this thread, a
        SQLAlchemy Session isn't thread-safe), (2) run every batch's LLM
        call CONCURRENTLY (no DB access at all), (3) apply every batch's
        result SEQUENTIALLY (DB writes, same thread-safety constraint).
        Per-batch behavior (prompt, repair, fail-soft fallback,
        degradation recording) is byte-for-byte unchanged from the
        original single-threaded loop -- only the LLM network call itself
        now overlaps across batches.
        """
        if not source_ids or not clarified_summary:
            return

        prepared_batches = []
        for i in range(0, len(source_ids), STANCE_BATCH_SIZE):
            batch_ids = source_ids[i : i + STANCE_BATCH_SIZE]
            prepared = self._prepare_stance_batch(batch_ids)
            if prepared is not None:
                prepared_batches.append(prepared)

        if not prepared_batches:
            return

        with ThreadPoolExecutor(max_workers=min(4, len(prepared_batches))) as executor:
            future_to_batch = {
                executor.submit(
                    self._run_stance_llm_call, report_id, clarified_summary, prepared
                ): prepared
                for prepared in prepared_batches
            }
            for future in as_completed(future_to_batch):
                prepared = future_to_batch[future]
                self._apply_stance_batch_result(report_id, prepared, future)

    def _prepare_stance_batch(self, batch_ids: list[str]) -> dict | None:
        """DB-safe (caller's thread only): builds the {id: Source} map and
        listing text for one batch. Returns None when there's nothing
        classifiable in this batch -- matches the original early-return."""
        sources = (
            self.db.query(models.Source)
            .filter(models.Source.id.in_(batch_ids))
            .all()
        )
        by_id = {source.id: source for source in sources}
        if not by_id:
            return None

        listing_lines = []
        for source_id in batch_ids:
            source = by_id.get(source_id)
            if not source:
                continue
            evidence = (
                self.db.query(models.SourceEvidence)
                .filter_by(source_id=source_id)
                .first()
            )
            quote = (evidence.snippet if evidence else "") or ""
            quote = quote.strip()[:400]
            if not quote:
                # Nothing to classify against (e.g. a patent, metadata
                # only) -- leave it at its provenance prior.
                continue
            listing_lines.append(f"- id: {source_id} | quote: {quote}")

        if not listing_lines:
            return None

        return {"batch_ids": batch_ids, "by_id": by_id, "listing_lines": listing_lines}

    def _run_stance_llm_call(
        self, report_id: str, clarified_summary: str, prepared: dict
    ) -> list[dict]:
        """No DB access at all -- safe to run concurrently across
        batches, unlike _prepare_stance_batch/_apply_stance_batch_result.
        Raises ValueError (bad/unparseable response, including after one
        repair attempt) or RuntimeError (generate_chat exhausted both Groq
        keys); the caller (_apply_stance_batch_result) applies the
        fail-soft fallback for both, and lets anything else (a real bug)
        propagate."""
        listing_lines = prepared["listing_lines"]
        prompt = (
            STANCE_CLASSIFICATION_PROMPT.replace(
                "{{CLARIFIED_SUMMARY}}", clarified_summary
            ).replace("{{SOURCES}}", "\n".join(listing_lines))
        )
        max_tokens = STANCE_TOKENS_BASE + STANCE_TOKENS_PER_SOURCE * len(listing_lines)

        def _generate_classifications(
            repair_reason: str | None, temperature: float
        ) -> list[dict]:
            call_prompt = prompt
            if repair_reason:
                call_prompt += (
                    "\n\nREPAIR REQUIRED:\n"
                    f"{repair_reason}\n"
                    "Regenerate the full JSON so the classifications are valid."
                )
            raw = generate_chat(
                messages=[{"role": "system", "content": call_prompt}],
                temperature=temperature,
                task="stance_classification",
                max_tokens=max_tokens,
            )
            data = parse_json_object(raw, label="Stance classification")
            classifications = data.get("classifications")
            if not isinstance(classifications, list):
                raise ValueError("Invalid classifications format")
            return classifications

        # Fix-audit Part 2: one repair attempt before this batch's
        # fallback (provenance prior) fires -- previously a single bad
        # response degraded the whole batch immediately.
        return generate_with_repair(
            generate=_generate_classifications,
            on_repair=lambda reason: logger.info(
                "[RESEARCH] Repairing failed stance classification "
                "report_id=%s reason=%s",
                report_id,
                reason,
            ),
        )

    def _apply_stance_batch_result(
        self, report_id: str, prepared: dict, future
    ) -> None:
        """DB-safe (caller's thread only): applies one batch's LLM result
        (or its fail-soft fallback) to Postgres. `future` is this batch's
        completed _run_stance_llm_call future -- calling .result() here
        (not inside the thread pool) re-raises any exception it holds on
        THIS thread, at the same point in the call graph the original
        single-threaded try/except used to catch it."""
        batch_ids = prepared["batch_ids"]
        by_id = prepared["by_id"]
        try:
            classifications = future.result()

            updated = 0
            for entry in classifications:
                if not isinstance(entry, dict):
                    continue
                source = by_id.get(entry.get("id"))
                stance = entry.get("stance")
                if not source or stance not in VALID_STANCES:
                    continue
                source.stance = stance
                rationale = entry.get("rationale")
                if isinstance(rationale, str) and rationale.strip():
                    source.stance_rationale = rationale.strip()[:500]
                updated += 1

            self.db.commit()
            logger.info(
                "[RESEARCH] Stance classification updated %d/%d sources for report_id=%s",
                updated,
                len(batch_ids),
                report_id,
            )
        except (ValueError, RuntimeError) as exc:
            # Fail-soft (Stage 2d's discipline, same rule here): a
            # classification failure must never drop a source. Every
            # source in this batch keeps the provenance prior it was
            # already given at ingestion, which defaults toward "neutral"
            # rather than dropping anything. Narrowed from bare Exception
            # (fix-audit Part 0 Rule 2): ValueError is a bad/unparseable
            # response, RuntimeError is generate_chat exhausting both Groq
            # keys -- a KeyError or DB error here is a real bug and must
            # surface, not be silently absorbed as if it were an LLM hiccup.
            self.db.rollback()
            record_degradation(report_id, "stance_classification", str(exc))
            logger.warning(
                "[RESEARCH] Stance classification failed for report_id=%s batch_size=%d reason=%s",
                report_id,
                len(batch_ids),
                exc,
                exc_info=True,
            )

    # --------------------------------------------------
    # SERP search
    # --------------------------------------------------
    def search(self, query: str, limit: int = 5) -> list[dict]:
        """
        Fetch organic search results from SerpAPI.

        2026-09-14 remediation Phase 4.4: the three engines are
        independent SerpAPI calls with no shared state -- run
        concurrently instead of one after another. This is ALREADY
        inside research_worker.py's own outer query-level ThreadPoolExecutor
        (up to 4 queries in flight); this adds a second, small level of
        concurrency within each query's own 3-engine fetch, which is safe
        since none of the three share mutable state with each other.
        """
        logger.info("Running SERP search for query: %s", query)

        with ThreadPoolExecutor(max_workers=3) as executor:
            web_future = executor.submit(self._google_web, query, limit)
            news_future = executor.submit(self._google_news, query, limit)
            patents_future = executor.submit(self._google_patents, query, limit)

            results: list[dict] = []
            for engine_name, future in (
                ("web", web_future),
                ("news", news_future),
                ("patents", patents_future),
            ):
                try:
                    results.extend(future.result())
                except Exception:
                    # _execute_serp already catches its own failures and
                    # returns [] -- this is a last-resort net so one
                    # engine's unexpected exception can't take the other
                    # two down with it.
                    logger.exception(
                        "[RESEARCH] SERP engine=%s failed for query=%s",
                        engine_name,
                        query,
                    )

        logger.info(
            "SERP returned %d total results for query=%s",
            len(results),
            query,
        )
        return results
    
    # --------------------------------------------------
    # SERP variants
    # --------------------------------------------------
    def _google_web(self, query: str, limit: int) -> List[Dict]:
        return self._execute_serp(
            params={
                "engine": "google",
                "q": query,
                "num": limit,
                "hl": "en",
                "gl": "us",
                "google_domain": "google.com",
                "api_key": settings.SERP_API_KEY,
            },
            source_type="web",
        )

    def _google_news(self, query: str, limit: int) -> List[Dict]:
        return self._execute_serp(
            params={
                "engine": "google",
                "q": query,
                "tbm": "nws",
                "num": limit,
                "hl": "en",
                "gl": "us",
                "api_key": settings.SERP_API_KEY,
            },
            source_type="news",
        )

    def _google_patents(self, query: str, limit: int) -> List[Dict]:
        # 2026-09-14 remediation Phase 4.4: was max(10, limit) -- a fixed
        # floor of 10 patent results per query regardless of the caller's
        # actual limit, even though research_worker.py never scrapes a
        # patent result at all (metadata-only, straight to a bare Source
        # row -- see run_research's PATENT branch). Matching `limit` like
        # the other two engines cuts this leg's SerpAPI payload/processing
        # cost without removing the feature -- patent evidence is still
        # genuinely relevant for some ideas (hardware, biotech).
        return self._execute_serp(
            params={
                "engine": "google",
                "q": query,
                "tbm": "pts",
                "num": limit,
                "api_key": settings.SERP_API_KEY,
            },
            source_type="patent",
        )

    # --------------------------------------------------
    # SERP executor
    # --------------------------------------------------
    def _execute_serp(
        self, params: dict, source_type: str, *, _is_retry: bool = False
    ) -> List[Dict]:
        try:
            search = GoogleSearch(params)
            data = search.get_dict()
        except Exception as e:
            logger.exception("SERP request failed (%s)", source_type)
            return []

        if "error" in data:
            error_message = str(data["error"])
            # 2026-09-14 remediation Phase 5 (audit §4.6): "We couldn't
            # get valid results for this search" was SerpAPI's own
            # service-side error on 9 calls in the audited run --
            # transient on their end, not a malformed request, so one
            # retry is worth it before giving up. Every other error
            # string still fails immediately (unchanged) -- most SerpAPI
            # errors ARE the request itself being wrong (bad api_key,
            # invalid params), which a retry would just repeat.
            if not _is_retry and "couldn't get valid results" in error_message.lower():
                logger.warning(
                    "SERP API transient error (%s), retrying once: %s",
                    source_type,
                    error_message,
                )
                return self._execute_serp(params, source_type, _is_retry=True)

            logger.error(
                "SERP API error (%s): %s",
                source_type,
                error_message,
            )
            return []

        results = []        
        # 👇 WEB + PATENTS
        if "organic_results" in data:
            results.extend(data["organic_results"])

        # 👇 NEWS-SPECIFIC
        if source_type == "news" and "news_results" in data:
            results.extend(data["news_results"])
            
        logger.debug(
            "SERP %s returned %d organic results",
            source_type,
            len(results),
        )
        normalized = []

        for r in results:
            link = r.get("link")
            if not link:
                continue

            normalized.append({
                "url": link,
                "domain": self._extract_domain(link),
                "title": r.get("title"),
                "snippet": r.get("snippet"),
                "type": source_type,
            })

        return normalized

    # --------------------------------------------------
    # URL Dedup (DB + in-memory)
    # --------------------------------------------------
    def is_duplicate_url(self, report_id: str, url: str) -> bool:
        return (
            self.db.query(models.Source)
            .filter_by(report_id=report_id, url=url)
            .first()
            is not None
        )
    
    # --------------------------------------------------
    # Create source metadata (Postgres)
    # --------------------------------------------------
    def create_source(
        self,
        report_id: str,
        data: dict,
        *,
        stance: str | None = None,
    ) -> models.Source:
        """`stance`, when given, is the Stage 3e provenance PRIOR --
        "challenges" for a source found by the counter pass, "neutral" for
        the main pass. Refined later, in a batch, by classify_stance()."""
        source = models.Source(
            report_id=report_id,
            url=data["url"],
            domain=data.get("domain"),
            # SERP already returns a real page title (_execute_serp
            # normalizes it into every result) -- Stage 5b, previously
            # discarded before persistence, so citations always fell back
            # to showing the bare domain.
            title=data.get("title"),
            type=data.get("type", "web"),
            stance=stance,
        )

        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        logger.debug("Created source id=%s url=%s", source.id, source.url)
        return source

    # --------------------------------------------------
    # Scrape + extract
    # --------------------------------------------------
    def scrape_and_extract(
        self, url: str, report_id: str | None = None
    ) -> tuple[list[str], str | None]:
        """Returns (chunks, cleaned_text). `chunks` is the WHOLE page split
        via chunk_text() (Stage 2a) -- deliberately not capped here the way
        the old "first 5 valid lines" extraction was, since that discarded
        everything below the fold (a market-research article's actual
        figures are rarely in the intro). Selection now happens at
        bundle-build time (EvidenceBundleService), which caps how many
        chunks from any one source enter a section's bundle -- see
        stratos-launch-plan Stage 2a.

        `report_id` is optional (mirrors TrendService.generate_queries) so
        existing call sites/tests keep working; pass it to have a scrape
        failure counted via record_degradation (fix-audit Part 0/5) -- a
        run where every scrape fails DNS used to be indistinguishable from
        a run where the pages were genuinely empty.
        """
        try:
            # SSRF guard: internet-supplied URLs must go through safe_get.
            resp = safe_get(url)
            if resp.status_code != 200:
                logger.warning(
                    "Non-200 response (%s) for url=%s",
                    resp.status_code,
                    url,
                )
                if report_id:
                    record_degradation(report_id, "web_scrape", f"non_200:{resp.status_code}")
                return [], None

            cleaned = clean_html(resp.text)
            chunks = chunk_text(cleaned)

            return chunks, cleaned

        except BlockedRequestError as exc:
            logger.warning("Skipping blocked url=%s reason=%s", url, exc)
            if report_id:
                # A DNS failure and an actual SSRF block are different
                # signals (fix-audit Part 5) -- keep them distinguishable
                # in the tally, not just in the safe_fetch log line.
                stage = "web_scrape_dns_failure" if "dns_resolution_failed" in str(exc) else "web_scrape_blocked"
                record_degradation(report_id, stage, str(exc))
            return [], None
        except Exception as exc:
            logger.exception("Failed to scrape url=%s", url)
            if report_id:
                record_degradation(report_id, "web_scrape", str(exc))
            return [], None

    # --------------------------------------------------
    # Save snippets (Postgres)
    # --------------------------------------------------
    def save_evidence(self, source_id: str, snippets: list[str]):
        for snippet in snippets:
            row = models.SourceEvidence(
                source_id=source_id,
                snippet=snippet,
            )
            self.db.add(row)

        self.db.commit()
        logger.debug(
            "Saved %d evidence snippets for source_id=%s",
            len(snippets),
            source_id,
        )

    # --------------------------------------------------
    # Save raw text (Astra)
    # --------------------------------------------------
    def save_to_astra(
        self,
        report_id: str,
        source_id: str,
        url: str,
        text: str,
        metadata: dict,
    ):
        """
        Fail-soft write to Astra `evidence`.
        Postgres remains the source of relational metadata for MVP.
        """
        if not text:
            return None

        evidence_id = str(uuid.uuid4())
        snippets = metadata.get("snippets") or []
        # The caller passes the full chunk list in `metadata["snippets"]`
        # only so the quality score below can be computed from it -- it must
        # not be persisted (gap-closing plan Stage 5: that is the same chunk
        # text `embeddings` already holds, and leaving it in `metadata`
        # keeps the very copy Stage 5 set out to remove, plus adds document
        # size the 8000-byte indexed-field limit then trips on).
        archive_metadata = {k: v for k, v in metadata.items() if k != "snippets"}
        document = {
            "evidence_id": evidence_id,
            "report_id": report_id,
            "source_id": source_id,
            "url": url,
            "title": metadata.get("title"),
            "domain": metadata.get("domain") or self._extract_domain(url),
            "type": metadata.get("type", "web"),
            "raw_text": _truncate_utf8_bytes(text, EVIDENCE_RAW_TEXT_MAX_BYTES),
            # No "snippets" key here (gap-closing plan Stage 5) -- the same
            # chunk text used to be written twice, once here as a bare
            # string list and again into the `embeddings` collection
            # (EmbeddingService.save_chunks, this source's chunks). This
            # doc keeps its role as the per-source archive (raw_text +
            # metadata); the lexical corpus reads from `embeddings`
            # instead (AstraEvidenceRepository.list_evidence_chunks),
            # which carries a real per-chunk id `snippets` never could.
            # `snippets` is kept locally, in-memory only, for the quality
            # score below -- it's just not persisted redundantly anymore.
            "metadata": archive_metadata,
            "ingestion_quality_score": self._ingestion_quality_score(
                text=text,
                snippets=snippets,
            ),
            "created_at": datetime.utcnow().isoformat(),
        }

        saved_id = self.astra_repository.save_evidence_document(document)
        if saved_id:
            logger.debug("[ASTRA] Saved evidence_id=%s source_id=%s", saved_id, source_id)

        return saved_id

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def _extract_domain(self, url: str) -> str:
        return url.split("//")[-1].split("/")[0]
    
    # --------------------------------------------------
    # Evidence quality helpers
    # --------------------------------------------------

    def _ingestion_quality_score(self, text: str, snippets: list[str]) -> float:
        """A per-document quality signal, independent of any section or
        idea -- NOT the per-section relevance ranking (see
        evidence_ranker.py). `useful_terms` was previously a hand-tuned
        lexicon for one freelancer-tool test idea ("upwork", "fiverr",
        "telegram", "discord"), silently applied to every report since --
        same bug class as SECTION_PREFERENCES/OFF_TOPIC_TERMS. Replaced
        with structural markers of substantive, citable content -- present
        regardless of topic -- rather than a domain-specific vocabulary.
        """
        haystack = " ".join([text[:3000], *snippets]).lower()
        score = 1.0

        substantive_markers = (
            "according to",
            "study",
            "survey",
            "report",
            "data",
            "research",
            "analysis",
            "market",
            "growth",
            "percent",
            "%",
        )
        score += sum(0.5 for term in substantive_markers if term in haystack)

        boilerplate_terms = (
            "checking your browser",
            "javascript is disabled",
            "you signed in",
            "you signed out",
            "oops",
            "free trial",
            "no credit card",
        )
        score -= sum(1.0 for term in boilerplate_terms if term in haystack)

        return max(score, 0.0)