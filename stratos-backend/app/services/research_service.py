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
from app.llm.client import generate_chat
from app.llm.prompts import RESEARCH_QUERY_PROMPT
from app.services.astra_evidence_repository import AstraEvidenceRepository
import json

import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


BAD_PREFIXES = (
    "home",
    "menu",
    "skip",
    "search",
    "login",
    "sign up",
    "subscribe",
    "filter",
    "where ?",
)

class ResearchService:
    def __init__(self, db: Session):
        self.db = db
        self.astra_repository = AstraEvidenceRepository()

    # --------------------------------------------------
    # Query generation
    # --------------------------------------------------
    def generate_queries(self, clarified_summary: str) -> list[str]:
        """
        Generate SERP queries using LLM.
        Fallback to deterministic queries on failure.
        """
        
        if not clarified_summary:
            raise ValueError("Clarified summary missing")

        prompt = RESEARCH_QUERY_PROMPT.replace(
            "{{CLARIFIED_SUMMARY}}",
            clarified_summary
        )

        try:
            raw = generate_chat(
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3,
                task="research_query",
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

            print("[RESEARCH] Generated queries:", cleaned[:5])
            
            return cleaned[:5]

        except Exception:
            # 🚑 SAFE FALLBACK — pipeline must continue
            return [
                "existing solutions",
                "competitor tools",
                "market overview",
            ]

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
    def create_source(self, report_id: str, data: dict) -> models.Source:
        source = models.Source(
            report_id=report_id,
            url=data["url"],
            domain=data.get("domain"),
            type=data.get("type", "web"),
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

            raw_lines = cleaned.split("\n")

            snippets = [
                line.strip()
                for line in raw_lines
                if self._is_valid_snippet(line)
            ][:5]

            return snippets, cleaned

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
        document = {
            "evidence_id": evidence_id,
            "report_id": report_id,
            "source_id": source_id,
            "url": url,
            "title": metadata.get("title"),
            "domain": metadata.get("domain") or self._extract_domain(url),
            "type": metadata.get("type", "web"),
            "raw_text": text[:50000],
            "snippets": snippets,
            "metadata": metadata,
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

    def _is_valid_snippet(self, text: str) -> bool:
        if not text:
            return False

        t = text.strip().lower()
        return (
            len(t) >= 40 and
            not t.startswith(BAD_PREFIXES)
        )

    def _ingestion_quality_score(self, text: str, snippets: list[str]) -> float:
        haystack = " ".join([text[:3000], *snippets]).lower()
        score = 1.0

        useful_terms = (
            "freelance",
            "upwork",
            "fiverr",
            "client",
            "hiring",
            "job",
            "telegram",
            "discord",
            "api",
            "monitor",
            "automation",
            "llm",
        )
        score += sum(0.5 for term in useful_terms if term in haystack)

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