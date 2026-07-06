from __future__ import annotations

import re
from typing import Any


BOILERPLATE_TERMS = (
    "checking your browser",
    "javascript is disabled",
    "you signed in",
    "you signed out",
    "you switched accounts",
    "oops! something went wrong",
    "free trial",
    "no credit card",
    "press enter",
    "accept cookies",
    "privacy policy",
)

OFF_TOPIC_TERMS = (
    "crypto",
    "dark web",
    "malware",
    "threat intelligence",
    "supply chain attack",
)

SECTION_PREFERENCES = {
    "problem": {
        "freelancer",
        "freelance",
        "upwork",
        "fiverr",
        "competition",
        "low-paying",
        "client",
        "job board",
        "pain",
        "workaround",
    },
    "persona": {
        "freelancer",
        "consultant",
        "agency",
        "solo",
        "client",
        "designer",
        "developer",
        "writer",
    },
    "solution": {
        "alternative",
        "platform",
        "tool",
        "solution",
        "marketplace",
        "job board",
        "scraper",
    },
    "competitor": {
        "competitor",
        "alternative",
        "pricing",
        "feature",
        "platform",
        "upwork",
        "fiverr",
        "toptal",
    },
    "trend": {
        "market",
        "trend",
        "growth",
        "industry",
        "news",
        "adoption",
        "freelance economy",
    },
    "opportunity": {
        "gap",
        "opportunity",
        "differentiation",
        "positioning",
        "high-ticket",
        "early",
        "intent",
    },
    "risk": {
        "risk",
        "constraint",
        "privacy",
        "api",
        "cost",
        "scalability",
        "compliance",
        "spam",
    },
    "technical": {
        "api",
        "python",
        "integration",
        "telegram",
        "discord",
        "reddit",
        "x",
        "llm",
        "monitor",
        "webhook",
        "automation",
    },
}

STOPWORDS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "of",
    "for",
    "to",
    "in",
    "on",
    "with",
    "by",
    "from",
}


class EvidenceRanker:
    def rank_for_section(
        self,
        *,
        clarified_summary: str,
        section_title: str,
        evidence_items: list[dict[str, Any]],
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        scored = []
        seen: set[str] = set()

        for item in evidence_items:
            normalized = self._normalize_item(item)
            quote = normalized.get("quote")
            source_id = normalized.get("source_id")
            if not quote or not source_id:
                continue

            fingerprint = quote.lower()[:180]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)

            score, reason = self._score_item(
                clarified_summary=clarified_summary,
                section_title=section_title,
                item=normalized,
            )
            if score <= 0:
                continue

            normalized["section_relevance_score"] = score
            normalized["reason"] = reason
            scored.append(normalized)

        scored.sort(
            key=lambda item: item["section_relevance_score"],
            reverse=True,
        )

        bundle_items = []
        for index, item in enumerate(scored[:limit], start=1):
            item["marker"] = f"CIT-{index:03d}"
            bundle_items.append(item)

        return bundle_items

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        quote = item.get("quote") or item.get("snippet") or item.get("text")
        return {
            "evidence_id": item.get("evidence_id")
            or item.get("astra_evidence_id")
            or item.get("_id"),
            "source_id": item.get("source_id"),
            "url": item.get("url"),
            "domain": item.get("domain"),
            "title": item.get("title") or item.get("domain") or item.get("url"),
            "type": item.get("type", "web"),
            "quote": str(quote).strip()[:1200] if quote else None,
        }

    def _score_item(
        self,
        *,
        clarified_summary: str,
        section_title: str,
        item: dict[str, Any],
    ) -> tuple[float, str]:
        haystack = " ".join(
            str(item.get(key, ""))
            for key in ("title", "type", "quote", "domain", "url")
        ).lower()

        score = 1.0
        reasons = []

        section_terms = self._section_terms(section_title)
        section_matches = [term for term in section_terms if term in haystack]
        if section_matches:
            score += len(section_matches) * 1.5
            reasons.append("section_terms=" + ",".join(section_matches[:4]))

        summary_terms = self._keywords(clarified_summary)
        summary_matches = [term for term in summary_terms if term in haystack]
        if summary_matches:
            score += min(len(summary_matches), 6) * 0.75
            reasons.append("summary_overlap")

        if item.get("type") == "news" and "trend" in section_title.lower():
            score += 1.0
            reasons.append("news_for_trends")

        penalties = [term for term in BOILERPLATE_TERMS if term in haystack]
        if penalties:
            score -= len(penalties) * 2.0
            reasons.append("boilerplate_penalty")

        off_topic = [term for term in OFF_TOPIC_TERMS if term in haystack]
        if off_topic:
            score -= len(off_topic) * 1.5
            reasons.append("off_topic_penalty")

        return score, ";".join(reasons) or "generic_match"

    def _section_terms(self, section_title: str) -> set[str]:
        normalized = section_title.lower()
        for key, terms in SECTION_PREFERENCES.items():
            if key in normalized:
                return terms

        return self._keywords(section_title)

    def _keywords(self, text: str) -> set[str]:
        return {
            word
            for word in re.findall(r"[a-zA-Z][a-zA-Z-]+", text.lower())
            if len(word) > 3 and word not in STOPWORDS
        }
