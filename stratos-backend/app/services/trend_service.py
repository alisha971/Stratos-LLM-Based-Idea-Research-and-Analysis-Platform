"""
Trend Service
- Aggregates trend evidence from four free, no-key providers:
  - Hacker News Algolia search
  - GDELT 2.0 DOC API (via gdeltdoc)
  - Google News RSS (via feedparser)
  - arXiv Atom API (via feedparser)
- Generates trend-focused queries from clarified summary (LLM with safe fallback).
- Deduplicates, caps, and persists to Postgres + (best-effort) Astra.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable
from urllib.parse import quote_plus

import requests
from sqlalchemy.orm import Session

from app.db import models
from app.llm.client import generate_chat
from app.llm.prompts import TREND_QUERY_PROMPT
from app.services.astra_evidence_repository import AstraEvidenceRepository

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
ARXIV_API_URL = "https://export.arxiv.org/api/query"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

CATEGORY_NEWS = "news"
CATEGORY_PAPERS = "papers"
CATEGORY_SOCIAL = "social"

PROVIDER_HN = "hn_algolia"
PROVIDER_GDELT = "gdelt"
PROVIDER_GOOGLE_NEWS = "google_news_rss"
PROVIDER_ARXIV = "arxiv"


class TrendService:
    def __init__(
        self,
        db: Session,
        astra_repository: AstraEvidenceRepository | None = None,
    ) -> None:
        self.db = db
        self.astra_repository = astra_repository or AstraEvidenceRepository()

    # --------------------------------------------------
    # Query generation
    # --------------------------------------------------
    def generate_queries(self, clarified_summary: str) -> list[str]:
        """
        Generate trend-focused queries via LLM.
        Falls back to deterministic queries on any failure.
        """
        if not clarified_summary:
            raise ValueError("Clarified summary missing")

        prompt = TREND_QUERY_PROMPT.replace(
            "{{CLARIFIED_SUMMARY}}",
            clarified_summary,
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

            logger.info("[TREND] Generated queries: %s", cleaned[:4])
            return cleaned[:4]

        except Exception:
            logger.exception("[TREND] Query generation failed; using fallback")
            return [
                "industry trends",
                "market growth",
                "recent news",
            ]

    # --------------------------------------------------
    # Provider fan-out wrapper
    # --------------------------------------------------
    def _run_provider_safe(
        self,
        fn: Callable[..., list[dict]],
        *args: Any,
        **kwargs: Any,
    ) -> list[dict]:
        try:
            return fn(*args, **kwargs) or []
        except Exception:
            logger.exception(
                "[TREND] Provider call failed: %s args=%s",
                getattr(fn, "__name__", str(fn)),
                args,
            )
            return []

    # --------------------------------------------------
    # Provider: Hacker News (Algolia search)
    # --------------------------------------------------
    def fetch_hackernews(self, query: str, limit: int = 10) -> list[dict]:
        cutoff = int((datetime.utcnow() - timedelta(days=90)).timestamp())
        params = {
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{cutoff}",
            "hitsPerPage": limit,
        }
        resp = requests.get(
            HN_SEARCH_URL,
            params=params,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(
                "[TREND] HN non-200 (%s) for query=%s",
                resp.status_code,
                query,
            )
            return []

        hits = resp.json().get("hits", [])
        items: list[dict] = []
        for h in hits:
            url = h.get("url") or (
                f"https://news.ycombinator.com/item?id={h.get('objectID')}"
                if h.get("objectID")
                else None
            )
            if not url:
                continue

            items.append(
                {
                    "title": (h.get("title") or "").strip(),
                    "url": url,
                    "summary": (h.get("story_text") or "")[:1000],
                    "published_at": _parse_datetime_safe(h.get("created_at")),
                    "provider": PROVIDER_HN,
                    "category": CATEGORY_SOCIAL,
                }
            )
        return items

    # --------------------------------------------------
    # Provider: GDELT 2.0 DOC API
    # --------------------------------------------------
    def fetch_gdelt(self, query: str, days: int = 90) -> list[dict]:
        try:
            from gdeltdoc import Filters, GdeltDoc
        except ImportError:
            logger.warning("[TREND] gdeltdoc not installed; skipping GDELT")
            return []

        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)

        filters = Filters(
            keyword=query,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )

        gd = GdeltDoc()
        df = gd.article_search(filters)

        if df is None or len(df) == 0:
            return []

        items: list[dict] = []
        for _, row in df.iterrows():
            url = row.get("url")
            if not url:
                continue

            items.append(
                {
                    "title": (row.get("title") or "").strip(),
                    "url": url,
                    "summary": str(row.get("domain") or ""),
                    "published_at": _parse_datetime_safe(row.get("seendate")),
                    "provider": PROVIDER_GDELT,
                    "category": CATEGORY_NEWS,
                }
            )
        return items

    # --------------------------------------------------
    # Provider: Google News RSS
    # --------------------------------------------------
    def fetch_google_news_rss(self, query: str, limit: int = 10) -> list[dict]:
        try:
            import feedparser
        except ImportError:
            logger.warning("[TREND] feedparser not installed; skipping Google News")
            return []

        feed_url = (
            f"{GOOGLE_NEWS_RSS_URL}?q={quote_plus(query)}"
            f"&hl=en-US&gl=US&ceid=US:en"
        )
        feed = feedparser.parse(feed_url)
        entries = (feed.entries or [])[:limit]

        items: list[dict] = []
        for e in entries:
            url = getattr(e, "link", None)
            if not url:
                continue

            items.append(
                {
                    "title": (getattr(e, "title", "") or "").strip(),
                    "url": url,
                    "summary": (getattr(e, "summary", "") or "")[:1000],
                    "published_at": _parse_struct_time_safe(
                        getattr(e, "published_parsed", None)
                    ),
                    "provider": PROVIDER_GOOGLE_NEWS,
                    "category": CATEGORY_NEWS,
                }
            )
        return items

    # --------------------------------------------------
    # Provider: arXiv
    # --------------------------------------------------
    def fetch_arxiv(self, query: str, limit: int = 10) -> list[dict]:
        try:
            import feedparser
        except ImportError:
            logger.warning("[TREND] feedparser not installed; skipping arXiv")
            return []

        feed_url = (
            f"{ARXIV_API_URL}?search_query=all:{quote_plus(query)}"
            f"&start=0&max_results={limit}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )
        feed = feedparser.parse(feed_url)
        entries = (feed.entries or [])[:limit]

        items: list[dict] = []
        for e in entries:
            url = getattr(e, "link", None)
            if not url:
                continue

            items.append(
                {
                    "title": (getattr(e, "title", "") or "").strip(),
                    "url": url,
                    "summary": (getattr(e, "summary", "") or "")[:2000],
                    "published_at": _parse_struct_time_safe(
                        getattr(e, "published_parsed", None)
                    ),
                    "provider": PROVIDER_ARXIV,
                    "category": CATEGORY_PAPERS,
                }
            )
        return items

    # --------------------------------------------------
    # Dedup + cap
    # --------------------------------------------------
    def dedupe_items(self, items: list[dict]) -> list[dict]:
        seen_urls: set[str] = set()
        seen_title_keys: set[tuple[str, str]] = set()
        deduped: list[dict] = []

        for item in items:
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip().lower()
            provider = item.get("provider") or ""

            if not url or not title:
                continue

            url_key = _normalize_url(url)
            title_key = (provider, title)

            if url_key in seen_urls or title_key in seen_title_keys:
                continue

            seen_urls.add(url_key)
            seen_title_keys.add(title_key)
            deduped.append(item)

        return deduped

    def cap_items(
        self,
        items: list[dict],
        max_per_category: int = 15,
    ) -> list[dict]:
        by_category: dict[str, list[dict]] = {}
        for item in items:
            by_category.setdefault(item.get("category", "news"), []).append(item)

        capped: list[dict] = []
        for category, group in by_category.items():
            group_sorted = sorted(
                group,
                key=lambda x: x.get("published_at") or datetime.min,
                reverse=True,
            )
            capped.extend(group_sorted[:max_per_category])

        return capped

    # --------------------------------------------------
    # Persistence: Postgres
    # --------------------------------------------------
    def persist_postgres(
        self,
        report_id: str,
        items: list[dict],
    ) -> dict[str, str]:
        """
        Group items by category, upsert one Trend row per category,
        insert TrendItem rows, return {category: trend_id} map.
        """
        trend_id_by_category: dict[str, str] = {}

        for item in items:
            category = item.get("category") or CATEGORY_NEWS
            trend_id = trend_id_by_category.get(category)

            if not trend_id:
                trend = (
                    self.db.query(models.Trend)
                    .filter_by(report_id=report_id, category=category)
                    .first()
                )
                if not trend:
                    trend = models.Trend(
                        id=str(uuid.uuid4()),
                        report_id=report_id,
                        category=category,
                    )
                    self.db.add(trend)
                    self.db.flush()
                trend_id = trend.id
                trend_id_by_category[category] = trend_id

            self.db.add(
                models.TrendItem(
                    id=str(uuid.uuid4()),
                    trend_id=trend_id,
                    title=item.get("title"),
                    url=item.get("url"),
                    summary=item.get("summary"),
                    published_at=item.get("published_at"),
                )
            )

        self.db.commit()
        logger.info(
            "[TREND] Persisted %d items across %d categories for report_id=%s",
            len(items),
            len(trend_id_by_category),
            report_id,
        )
        return trend_id_by_category

    # --------------------------------------------------
    # Persistence: Astra
    # --------------------------------------------------
    def persist_astra(
        self,
        report_id: str,
        items: list[dict],
        trend_id_by_category: dict[str, str],
    ) -> int:
        if not self.astra_repository.enabled:
            logger.info("[TREND] Astra disabled; skipping trend_items mirror")
            return 0

        saved = 0
        for item in items:
            category = item.get("category") or CATEGORY_NEWS
            trend_id = trend_id_by_category.get(category)

            doc = {
                "trend_item_id": str(uuid.uuid4()),
                "report_id": report_id,
                "trend_id": trend_id,
                "category": category,
                "provider": item.get("provider"),
                "title": item.get("title"),
                "url": item.get("url"),
                "summary": item.get("summary"),
                "text": item.get("summary") or item.get("title"),
                "published_at": _isoformat_safe(item.get("published_at")),
                "created_at": datetime.utcnow().isoformat(),
            }

            if self.astra_repository.save_trend_item(doc):
                saved += 1

        logger.info(
            "[TREND] Mirrored %d/%d items to Astra for report_id=%s",
            saved,
            len(items),
            report_id,
        )
        return saved


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def _normalize_url(url: str) -> str:
    u = url.strip().lower()
    if u.endswith("/"):
        u = u[:-1]
    return u


def _parse_datetime_safe(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value

    s = str(value).strip()
    if not s:
        return None

    # ISO-8601 with optional Z
    try:
        if s.endswith("Z"):
            s_norm = s[:-1] + "+00:00"
        else:
            s_norm = s
        return datetime.fromisoformat(s_norm).replace(tzinfo=None)
    except Exception:
        pass

    # GDELT seendate: YYYYMMDDTHHMMSSZ
    try:
        return datetime.strptime(s.rstrip("Z"), "%Y%m%dT%H%M%S")
    except Exception:
        pass

    # GDELT seendate without time
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        pass

    return None


def _parse_struct_time_safe(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(value))
    except Exception:
        return None


def _isoformat_safe(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
