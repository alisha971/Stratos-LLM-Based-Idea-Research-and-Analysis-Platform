# TODO: Integrate SERP API (SerpAPI / Bing / Brave)
# TODO: Domain filtering (wikipedia, blogs, product pages)
# TODO: Duplicate URL detection
# TODO: Rate limiting
# TODO: Timeout handling

# app/services/research_service.py

import uuid
import requests
from sqlalchemy.orm import Session

from app.db import models
from app.utils.text_cleaner import clean_html
from app.llm.client import generate_chat
from app.llm.prompts import RESEARCH_QUERY_PROMPT
import json

class ResearchService:
    def __init__(self, db: Session):
        self.db = db

    # --------------------------------------------------
    # Query generation
    # --------------------------------------------------
    def generate_queries(self, clarified_summary: str) -> list[str]:
        """
        MVP: deterministic queries
        TODO: derive queries from clarified_summary
        """
        return [
            "existing solutions",
            "competitor tools",
            "market overview",
        ]

    # --------------------------------------------------
    # SERP search
    # --------------------------------------------------
    def search(self, query: str) -> list[dict]:
        """
        TODO: integrate real SERP provider
        """
        return [
            {
                "url": "https://example.com",
                "domain": "example.com",
                "title": "Example Product",
                "type": "web",
            }
        ]

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
        # exists = (
        #     self.db.query(models.Source)
        #     .filter_by(report_id=report_id, url=data["url"])
        #     .first()
        # )
        # if exists:
        #     return exists
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    # --------------------------------------------------
    # Scrape + extract
    # --------------------------------------------------
    def scrape_and_extract(self, url: str) -> tuple[list[str], str | None]:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return [], None

            cleaned = clean_html(resp.text)

            snippets = cleaned.split("\n")[:5]  # MVP heuristic

            return snippets, cleaned

        except Exception:
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
