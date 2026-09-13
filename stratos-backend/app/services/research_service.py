# TODO: Integrate SERP API (SerpAPI / Bing / Brave)
# TODO: Domain filtering (wikipedia, blogs, product pages)
# TODO: Duplicate URL detection
# TODO: Rate limiting
# TODO: Timeout handling

# app/services/research_service.py

import uuid
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
from app.llm.client import generate_chat
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
        if not source_ids or not clarified_summary:
            return

        for i in range(0, len(source_ids), STANCE_BATCH_SIZE):
            batch_ids = source_ids[i : i + STANCE_BATCH_SIZE]
            self._classify_stance_batch(report_id, clarified_summary, batch_ids)

    def _classify_stance_batch(
        self,
        report_id: str,
        clarified_summary: str,
        batch_ids: list[str],
    ) -> None:
        sources = (
            self.db.query(models.Source)
            .filter(models.Source.id.in_(batch_ids))
            .all()
        )
        by_id = {source.id: source for source in sources}
        if not by_id:
            return

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
            return

        prompt = (
            STANCE_CLASSIFICATION_PROMPT.replace(
                "{{CLARIFIED_SUMMARY}}", clarified_summary
            ).replace("{{SOURCES}}", "\n".join(listing_lines))
        )

        try:
            raw = generate_chat(
                messages=[{"role": "system", "content": prompt}],
                temperature=0.2,
                task="stance_classification",
            )
            data = json.loads(raw)
            classifications = data.get("classifications")
            if not isinstance(classifications, list):
                raise ValueError("Invalid classifications format")

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
        except Exception:
            # Fail-soft (Stage 2d's discipline, same rule here): a
            # classification failure must never drop a source. Every
            # source in this batch keeps the provenance prior it was
            # already given at ingestion, which defaults toward "neutral"
            # rather than dropping anything.
            self.db.rollback()
            logger.warning(
                "[RESEARCH] Stance classification failed for report_id=%s batch_size=%d",
                report_id,
                len(batch_ids),
                exc_info=True,
            )

    # --------------------------------------------------
    # SERP search
    # --------------------------------------------------
    def search(self, query: str, limit: int = 5) -> list[dict]:
        """
        Fetch organic search results from SerpAPI.
        """
        logger.info("Running SERP search for query: %s", query)

        results = []
        results.extend(self._google_web(query, limit))
        results.extend(self._google_news(query, limit))
        results.extend(self._google_patents(query, limit))


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
        return self._execute_serp(
            params={
                "engine": "google",
                "q": query,
                "tbm": "pts",
                "num": max(10, limit),
                "api_key": settings.SERP_API_KEY,
            },
            source_type="patent",
        )

    # --------------------------------------------------
    # SERP executor
    # --------------------------------------------------
    def _execute_serp(self, params: dict, source_type: str) -> List[Dict]:
        try:
            search = GoogleSearch(params)
            data = search.get_dict()
        except Exception as e:
            logger.exception("SERP request failed (%s)", source_type)
            return []

        if "error" in data:
            logger.error(
                "SERP API error (%s): %s",
                source_type,
                data["error"],
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
    def scrape_and_extract(self, url: str) -> tuple[list[str], str | None]:
        """Returns (chunks, cleaned_text). `chunks` is the WHOLE page split
        via chunk_text() (Stage 2a) -- deliberately not capped here the way
        the old "first 5 valid lines" extraction was, since that discarded
        everything below the fold (a market-research article's actual
        figures are rarely in the intro). Selection now happens at
        bundle-build time (EvidenceBundleService), which caps how many
        chunks from any one source enter a section's bundle -- see
        stratos-launch-plan Stage 2a.
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
                return [], None

            cleaned = clean_html(resp.text)
            chunks = chunk_text(cleaned)

            return chunks, cleaned

        except BlockedRequestError as exc:
            logger.warning("Skipping blocked url=%s reason=%s", url, exc)
            return [], None
        except Exception:
            logger.exception("Failed to scrape url=%s", url)
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