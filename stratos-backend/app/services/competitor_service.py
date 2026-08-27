"""
Competitor Service
- Discovers candidate competing products from two free, no-key-required-ish
  launch surfaces: Product Hunt (GraphQL v2, needs a free developer token) and
  Hacker News "Show HN" (Algolia search, no key).
- Every candidate is verified by an actual SSRF-guarded homepage fetch before
  it is ever profiled or persisted — this is the anti-hallucination wall.
  A candidate that fails verification is dropped, never shown to the user.
- Persists a Postgres Source + Competitor + CompetitorFeature per verified
  competitor, and mirrors a flattened profile to Astra `competitor_insights`
  in the shape the section writer's evidence pipeline expects.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from app.config import settings
from app.db import models
from app.llm.client import generate_chat
from app.llm.prompts import (
    COMPETITOR_PROFILE_PROMPT,
    COMPETITOR_RELEVANCE_PROMPT,
    COMPETITOR_TERMS_PROMPT,
)
from app.services.astra_evidence_repository import AstraEvidenceRepository
from app.services.embedding_service import CONTENT_TYPE_COMPETITOR_PROFILE, EmbeddingService
from app.utils.safe_fetch import BlockedRequestError, safe_get
from app.utils.text_cleaner import clean_html

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


PRODUCT_HUNT_API_URL = "https://api.producthunt.com/v2/api/graphql"
HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

PROVIDER_PRODUCT_HUNT = "product_hunt"
PROVIDER_SHOW_HN = "show_hn"

# Must match the hardcoded core section title in outline_worker.py.
COMPETITOR_SECTION_TITLE = "Competitor Landscape"

# Deterministic, LLM-free — the section writer is explicitly barred from
# discussing the research process, so this caveat is appended by the
# assembler/export workers instead. Intentionally does not name the
# discovery platforms.
COMPETITOR_COVERAGE_NOTE = (
    "This landscape covers comparable products identified during research "
    "and is not exhaustive; similar products without a public launch "
    "presence may not be represented."
)

# How many relevance-ranked candidates to attempt verification on. Larger
# than COMPETITOR_MAX because verification (a real homepage fetch) drops a
# fraction of candidates — dead links, SSRF-blocked hosts, JS-only pages.
VERIFICATION_POOL_MULTIPLIER = 2

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your",
    "their", "will", "have", "has", "are", "was", "were", "you", "our",
}

_PH_TOPICS_QUERY = """
query TopicSearch($query: String!) {
  topics(query: $query, first: 3) {
    edges {
      node {
        slug
      }
    }
  }
}
"""

_PH_POSTS_QUERY = """
query PostsByTopic($slug: String!) {
  posts(topic: $slug, order: VOTES, first: 15) {
    edges {
      node {
        name
        tagline
        website
        votesCount
      }
    }
  }
}
"""


class CompetitorService:
    def __init__(
        self,
        db: Session,
        astra_repository: AstraEvidenceRepository | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.db = db
        self.astra_repository = astra_repository or AstraEvidenceRepository()
        self.embedding_service = embedding_service or EmbeddingService(
            self.astra_repository
        )

    # --------------------------------------------------
    # Term derivation
    # --------------------------------------------------
    def derive_search_terms(self, clarified_summary: str) -> dict[str, Any]:
        """
        Generate a category label + search keywords via LLM.
        Falls back to deterministic keyword extraction on any failure.
        """
        if not clarified_summary:
            raise ValueError("Clarified summary missing")

        prompt = COMPETITOR_TERMS_PROMPT.replace(
            "{{CLARIFIED_SUMMARY}}",
            clarified_summary,
        )

        try:
            raw = generate_chat(
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3,
                task="competitor_terms",
            )

            data = json.loads(raw)
            keywords = data.get("keywords")

            if not isinstance(keywords, list) or not keywords:
                raise ValueError("Invalid keywords format")

            cleaned = [
                k.strip() for k in keywords
                if isinstance(k, str) and k.strip()
            ][:5]

            if not cleaned:
                raise ValueError("No valid keywords")

            category = data.get("category")
            product_kind = data.get("product_kind")

            return {
                "category": category.strip() if isinstance(category, str) and category.strip() else cleaned[0],
                "keywords": cleaned,
                "product_kind": product_kind.strip() if isinstance(product_kind, str) else "",
            }

        except Exception:
            logger.exception("[COMPETITOR] Term derivation failed; using fallback")
            return {
                "category": "similar products",
                "keywords": _fallback_keywords(clarified_summary),
                "product_kind": "",
            }

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
                "[COMPETITOR] Provider call failed: %s args=%s",
                getattr(fn, "__name__", str(fn)),
                args,
            )
            return []

    # --------------------------------------------------
    # Provider: Product Hunt (GraphQL v2)
    # --------------------------------------------------
    def fetch_product_hunt(self, keyword: str) -> list[dict]:
        if not settings.PRODUCT_HUNT_TOKEN:
            return []

        headers = {
            "Authorization": f"Bearer {settings.PRODUCT_HUNT_TOKEN}",
            "Content-Type": "application/json",
        }

        # Product Hunt has no free-text post search — only topics(query:)
        # matches text ("select Topics whose name or aliases match the given
        # string"). So discovery goes keyword -> topic slugs -> top-voted
        # posts within those topics.
        topics_resp = requests.post(
            PRODUCT_HUNT_API_URL,
            json={"query": _PH_TOPICS_QUERY, "variables": {"query": keyword}},
            headers=headers,
            timeout=10,
        )
        if topics_resp.status_code != 200:
            logger.warning(
                "[COMPETITOR] PH topics non-200 (%s) for keyword=%s",
                topics_resp.status_code,
                keyword,
            )
            return []

        topics_data = topics_resp.json()
        if topics_data.get("errors"):
            logger.warning(
                "[COMPETITOR] PH topics error for keyword=%s: %s",
                keyword,
                topics_data["errors"],
            )
            return []

        slugs = [
            edge["node"]["slug"]
            for edge in topics_data.get("data", {}).get("topics", {}).get("edges", [])
            if edge.get("node", {}).get("slug")
        ]

        items: list[dict] = []
        for slug in slugs:
            posts_resp = requests.post(
                PRODUCT_HUNT_API_URL,
                json={"query": _PH_POSTS_QUERY, "variables": {"slug": slug}},
                headers=headers,
                timeout=10,
            )
            if posts_resp.status_code != 200:
                logger.warning(
                    "[COMPETITOR] PH posts non-200 (%s) for slug=%s",
                    posts_resp.status_code,
                    slug,
                )
                continue

            posts_data = posts_resp.json()
            if posts_data.get("errors"):
                logger.warning(
                    "[COMPETITOR] PH posts error for slug=%s: %s",
                    slug,
                    posts_data["errors"],
                )
                continue

            for edge in posts_data.get("data", {}).get("posts", {}).get("edges", []):
                node = edge.get("node") or {}
                website = node.get("website")
                name = node.get("name")
                if not website or not name:
                    continue

                items.append(
                    {
                        "name": name,
                        "tagline": node.get("tagline"),
                        "url": website,
                        "provider": PROVIDER_PRODUCT_HUNT,
                        "votes": node.get("votesCount") or 0,
                    }
                )

        return items

    # --------------------------------------------------
    # Provider: Hacker News "Show HN" (Algolia search)
    # --------------------------------------------------
    def fetch_show_hn(self, keyword: str, limit: int = 15) -> list[dict]:
        params = {
            "query": keyword,
            "tags": "show_hn",
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
                "[COMPETITOR] HN non-200 (%s) for keyword=%s",
                resp.status_code,
                keyword,
            )
            return []

        data = resp.json()
        items: list[dict] = []
        for hit in data.get("hits", []):
            url = hit.get("url")
            title = hit.get("title")
            if not url or not title:
                # Self-posts (Ask HN-style Show HN with no external link)
                # have nothing to verify against — skip.
                continue

            name, tagline = _parse_show_hn_title(title)
            items.append(
                {
                    "name": name,
                    "tagline": tagline,
                    "url": url,
                    "provider": PROVIDER_SHOW_HN,
                    "votes": hit.get("points") or 0,
                }
            )

        return items

    # --------------------------------------------------
    # Cheap pre-fetch dedupe
    # --------------------------------------------------
    def dedupe_candidates(self, items: list[dict]) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        deduped: list[dict] = []

        for item in items:
            name = (item.get("name") or "").strip()
            url = (item.get("url") or "").strip()
            if not name or not url:
                continue

            key = (name.lower(), _normalize_url(url))
            if key in seen:
                continue
            seen.add(key)

            candidate = dict(item)
            candidate["id"] = uuid.uuid4().hex[:8]
            deduped.append(candidate)

        return deduped

    # --------------------------------------------------
    # Relevance filter (LLM)
    # --------------------------------------------------
    def filter_relevant(
        self,
        clarified_summary: str,
        candidates: list[dict],
        pool_size: int,
    ) -> list[dict]:
        """
        Rank candidates by how comparable they are to the described idea.
        Falls back to a vote-sorted slice on any LLM failure — never blocks
        the pipeline on this step.
        """
        if not candidates:
            return []

        by_id = {c["id"]: c for c in candidates}
        listing = "\n".join(
            f"- id: {c['id']} | name: {c.get('name')} | tagline: {c.get('tagline') or ''} "
            f"| domain: {_domain_of(c.get('url') or '')}"
            for c in candidates
        )

        prompt = (
            COMPETITOR_RELEVANCE_PROMPT
            .replace("{{CLARIFIED_SUMMARY}}", clarified_summary)
            .replace("{{CANDIDATES}}", listing)
            .replace("{{MAX_COMPETITORS}}", str(pool_size))
        )

        try:
            raw = generate_chat(
                messages=[{"role": "system", "content": prompt}],
                temperature=0.2,
                task="competitor_relevance",
            )
            data = json.loads(raw)
            ids = data.get("relevant_ids")
            if not isinstance(ids, list) or not ids:
                raise ValueError("Invalid relevant_ids format")

            ranked = [by_id[i] for i in ids if i in by_id][:pool_size]
            if not ranked:
                raise ValueError("No known ids in relevant_ids")

            return ranked

        except Exception:
            logger.exception("[COMPETITOR] Relevance filter failed; using vote-sorted fallback")
            return sorted(
                candidates,
                key=lambda c: c.get("votes") or 0,
                reverse=True,
            )[:pool_size]

    # --------------------------------------------------
    # Verification (the anti-hallucination wall)
    # --------------------------------------------------
    def verify(self, candidate: dict) -> tuple[str | None, str | None, str | None]:
        """
        Fetch the candidate's homepage through the SSRF-guarded fetcher.
        Returns (resolved_url, homepage_text, pricing_text). resolved_url is
        None if verification fails, in which case the candidate MUST be
        dropped — never profiled or persisted on an unverified claim.
        """
        url = candidate.get("url")
        if not url:
            return None, None, None

        try:
            resp = safe_get(url)
            if resp.status_code != 200:
                logger.info(
                    "[COMPETITOR] Verification non-200 (%s) for url=%s",
                    resp.status_code,
                    url,
                )
                return None, None, None

            homepage_text = clean_html(resp.text)
            if len(homepage_text) < 200:
                logger.info(
                    "[COMPETITOR] Verification found no extractable text url=%s",
                    url,
                )
                return None, None, None

            resolved_url = resp.url or url

        except BlockedRequestError as exc:
            logger.info("[COMPETITOR] Verification blocked url=%s reason=%s", url, exc)
            return None, None, None
        except Exception:
            logger.exception("[COMPETITOR] Verification failed url=%s", url)
            return None, None, None

        pricing_text: str | None = None
        try:
            pricing_resp = safe_get(resolved_url.rstrip("/") + "/pricing")
            if pricing_resp.status_code == 200:
                pricing_text = clean_html(pricing_resp.text)
        except Exception:
            # Optional enrichment only — a missing/blocked /pricing page is
            # expected far more often than not and must never fail the
            # candidate.
            pass

        return resolved_url, homepage_text, pricing_text

    # --------------------------------------------------
    # Post-verification dedupe by registrable domain
    # --------------------------------------------------
    def dedupe_by_domain(self, verified: list[dict]) -> list[dict]:
        try:
            import tldextract
        except ImportError:
            logger.warning("[COMPETITOR] tldextract not installed; skipping domain dedupe")
            return verified

        seen: set[str] = set()
        deduped: list[dict] = []
        for item in sorted(verified, key=lambda c: c.get("votes") or 0, reverse=True):
            ext = tldextract.extract(item["resolved_url"])
            domain = ".".join(part for part in (ext.domain, ext.suffix) if part)
            if not domain or domain in seen:
                continue
            seen.add(domain)
            item["domain"] = domain
            deduped.append(item)

        return deduped

    # --------------------------------------------------
    # Profile (LLM, one call per verified competitor)
    # --------------------------------------------------
    def profile(
        self,
        candidate: dict,
        homepage_text: str,
        pricing_text: str | None,
    ) -> dict[str, Any]:
        prompt = (
            COMPETITOR_PROFILE_PROMPT
            .replace("{{CANDIDATE_NAME}}", candidate.get("name") or "")
            .replace("{{HOMEPAGE_TEXT}}", homepage_text[:5000])
            .replace("{{PRICING_TEXT}}", (pricing_text or "")[:3000])
        )

        try:
            raw = generate_chat(
                messages=[{"role": "system", "content": prompt}],
                temperature=0.2,
                task="competitor_profile",
            )
            data = json.loads(raw)

            return {
                "name": _clean_str(data.get("name")) or candidate.get("name"),
                "tagline": _clean_str(data.get("tagline")) or candidate.get("tagline"),
                "target_customer": _clean_str(data.get("target_customer")),
                "key_features": _clean_str_list(data.get("key_features"))[:5],
                "pricing_model": _clean_str(data.get("pricing_model")),
                "pricing_signal": _clean_str(data.get("pricing_signal")),
                "differentiators": _clean_str_list(data.get("differentiators"))[:3],
            }

        except Exception:
            logger.exception(
                "[COMPETITOR] Profiling failed for candidate=%s; using minimal profile",
                candidate.get("name"),
            )
            # Fail-soft minimal profile — grounded in nothing but the
            # verified name/tagline, never a guess.
            return {
                "name": candidate.get("name"),
                "tagline": candidate.get("tagline"),
                "target_customer": None,
                "key_features": [],
                "pricing_model": None,
                "pricing_signal": None,
                "differentiators": [],
            }

    # --------------------------------------------------
    # Persistence: Postgres
    # --------------------------------------------------
    def persist_postgres(
        self,
        report_id: str,
        verified_profiles: list[dict],
    ) -> list[dict]:
        """
        For each verified+profiled competitor, create a Source (so the
        profile is citable — Citation.source_id is a FK to sources.id),
        a Competitor row, and CompetitorFeature rows for its
        features/differentiators. Returns the list with `source_id` and
        `competitor_id` filled in for the Astra mirror step.
        """
        persisted: list[dict] = []

        for entry in verified_profiles:
            profile = entry["profile"]
            resolved_url = entry["resolved_url"]
            domain = entry.get("domain") or _domain_of(resolved_url)

            source = models.Source(
                id=str(uuid.uuid4()),
                report_id=report_id,
                url=resolved_url,
                domain=domain,
                type="competitor",
            )
            self.db.add(source)
            self.db.flush()

            summary_parts = [profile.get("tagline")]
            if profile.get("target_customer"):
                summary_parts.append(f"For: {profile['target_customer']}")
            if profile.get("key_features"):
                summary_parts.append("Features: " + ", ".join(profile["key_features"]))
            summary = " | ".join(p for p in summary_parts if p)

            competitor = models.Competitor(
                id=str(uuid.uuid4()),
                report_id=report_id,
                name=profile.get("name"),
                website=resolved_url,
                summary=summary or None,
                tagline=profile.get("tagline"),
                target_customer=profile.get("target_customer"),
                pricing_model=profile.get("pricing_model"),
                pricing_signal=profile.get("pricing_signal"),
                source_id=source.id,
            )
            self.db.add(competitor)
            self.db.flush()

            for feature in profile.get("key_features") or []:
                self.db.add(
                    models.CompetitorFeature(
                        id=str(uuid.uuid4()),
                        competitor_id=competitor.id,
                        feature=feature,
                        strength=None,
                        weakness=None,
                    )
                )
            for differentiator in profile.get("differentiators") or []:
                self.db.add(
                    models.CompetitorFeature(
                        id=str(uuid.uuid4()),
                        competitor_id=competitor.id,
                        feature=differentiator,
                        strength=differentiator,
                        weakness=None,
                    )
                )

            persisted.append(
                {
                    **entry,
                    "source_id": source.id,
                    "competitor_id": competitor.id,
                    "domain": domain,
                }
            )

        self.db.commit()
        return persisted

    # --------------------------------------------------
    # Persistence: Astra mirror
    # --------------------------------------------------
    def persist_astra(self, report_id: str, persisted: list[dict]) -> int:
        if not self.astra_repository.enabled:
            return 0

        saved = 0
        for entry in persisted:
            profile = entry["profile"]
            text_parts = [profile.get("tagline")]
            if profile.get("target_customer"):
                text_parts.append(f"Target customer: {profile['target_customer']}")
            if profile.get("key_features"):
                text_parts.append("Key features: " + ", ".join(profile["key_features"]))
            if profile.get("pricing_signal"):
                text_parts.append(f"Pricing: {profile['pricing_signal']}")
            if profile.get("differentiators"):
                text_parts.append("Differentiators: " + ", ".join(profile["differentiators"]))
            text = ". ".join(p for p in text_parts if p) or profile.get("name") or ""

            doc = {
                "insight_id": str(uuid.uuid4()),
                "report_id": report_id,
                "source_id": entry["source_id"],
                "competitor_id": entry["competitor_id"],
                "type": "competitor",
                "title": profile.get("name"),
                "url": entry["resolved_url"],
                "domain": entry.get("domain"),
                "text": text,
                "quote": text,
                "created_at": datetime.utcnow().isoformat(),
            }

            if self.astra_repository.save_competitor_insight(doc):
                saved += 1

        logger.info(
            "[COMPETITOR] Mirrored %d/%d insights to Astra for report_id=%s",
            saved,
            len(persisted),
            report_id,
        )
        return saved


# --------------------------------------------------
# Module-level helpers
# --------------------------------------------------
def _normalize_url(url: str) -> str:
    u = url.strip().lower()
    if u.endswith("/"):
        u = u[:-1]
    return u


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _parse_show_hn_title(title: str) -> tuple[str, str | None]:
    stripped = re.sub(r"(?i)^show hn:\s*", "", title).strip()
    for sep in (" – ", " — ", " - "):
        if sep in stripped:
            name, _, tagline = stripped.partition(sep)
            return name.strip(), tagline.strip() or None
    return stripped, None


def _clean_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _clean_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _fallback_keywords(clarified_summary: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{4,}", clarified_summary.lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for word in words:
        if word in STOPWORDS or word in seen:
            continue
        seen.add(word)
        keywords.append(word)
        if len(keywords) >= 3:
            break

    return keywords or ["software tools"]
