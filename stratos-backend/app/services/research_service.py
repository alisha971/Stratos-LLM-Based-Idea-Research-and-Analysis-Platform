# TODO: Integrate SERP API (SerpAPI / Bing / Brave)
# TODO: Domain filtering (wikipedia, blogs, product pages)
# TODO: Duplicate URL detection
# TODO: Rate limiting
# TODO: Timeout handling

# app/services/research_service.py

import uuid
import requests
from sqlalchemy.orm import Session
from serpapi import GoogleSearch
from typing import List, Dict

from app.db import models
from app.config import settings
from app.utils.text_cleaner import clean_html
from app.llm.client import generate_chat
from app.llm.prompts import RESEARCH_QUERY_PROMPT
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
            resp = requests.get(
                url,
                timeout=10,
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
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
        TODO:
        - Insert into Astra 'evidence' collection
        - Include full cleaned text
        """
        pass

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