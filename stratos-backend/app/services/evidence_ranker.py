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

# Section RHETORICAL PURPOSE, in plain prose -- not a hand-tuned keyword
# list for any one domain. This is the fix for the bug where the previous
# SECTION_PREFERENCES/OFF_TOPIC_TERMS dicts were tuned against one
# freelancer-tool test idea and silently applied to every report since: a
# medical-residents meal-prep idea got scored against "upwork"/"fiverr"
# vocabulary, and a fintech/security idea got its most relevant evidence
# actively suppressed by OFF_TOPIC_TERMS penalizing "crypto"/"malware".
#
# All TOPICAL signal comes from `clarified_summary` overlap (per-report by
# construction, see _score_item). These intent strings describe what a
# section is rhetorically *for*, independent of what the idea is about, and
# serve two purposes:
#   1. Structural lexical terms below are extracted mechanically from them
#      (via _keywords), never hand-picked per domain.
#   2. They ARE the semantic query text for Stage 2's vector search --
#      section_intent() is the public entry point EvidenceBundleService
#      uses to ask Astra "what evidence looks like a match for this
#      section's purpose", independent of ranking the section's title
#      words directly (which would just re-embed "Risks & Open Questions").
#
# Keys are matched as substrings of the (lowercased) section title, same
# lookup as before. Covers the 7 fixed CORE_SECTIONS plus the 3
# ALLOWED_OPTIONAL_SECTIONS (see outline_worker.py) that have historically
# been generated; a title matching none of these falls back to keyword
# extraction from the title itself (_section_terms), same as before.
SECTION_INTENTS: dict[str, str] = {
    "problem": (
        "the problem being solved, who experiences it, how painful it is, "
        "and what workarounds people currently use"
    ),
    "persona": (
        "who the target users are, their segment, context, and constraints"
    ),
    "solution": (
        "existing solutions and alternatives already available, and their "
        "strengths and weaknesses"
    ),
    "competitor": (
        "named competitors, their pricing, features, and positioning in "
        "the market"
    ),
    "trend": (
        "market size, growth rate, adoption trends, and industry momentum"
    ),
    # "opportunit" (stem, not "opportunity") deliberately matches both
    # "Opportunity" and "Opportunities" -- CORE_SECTIONS uses the plural
    # ("Opportunities & Gaps"), and "opportunity" is NOT a substring of
    # "opportunities" (...unity vs ...unities), so the singular form here
    # silently never matched the actual outline section title. Same latent
    # bug existed under this key in the pre-Stage-2 SECTION_PREFERENCES
    # dict; caught here by test_evidence_ranker.py's round-trip test.
    "opportunit": (
        "gaps in the market, unmet needs, and opportunities for "
        "differentiation"
    ),
    "risk": (
        "risks, constraints, costs, compliance burden, and open questions "
        "that could block this idea"
    ),
    "technical": (
        "technical feasibility, integration requirements, and "
        "implementation constraints"
    ),
    "regulatory": (
        "regulatory requirements, compliance obligations, and legal "
        "constraints"
    ),
    "go-to-market": (
        "go-to-market strategy, distribution channels, and customer "
        "acquisition approach"
    ),
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


def section_intent(section_title: str) -> str:
    """The natural-language description of what `section_title` is
    rhetorically for -- used as the Stage 2 semantic search query. Falls
    back to the title itself for a section that matches no known intent
    (an LLM-invented optional title outside ALLOWED_OPTIONAL_SECTIONS)."""
    normalized = section_title.lower()
    for key, intent in SECTION_INTENTS.items():
        if key in normalized:
            return intent
    return section_title


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

    def rank_ids_for_section(
        self,
        *,
        clarified_summary: str,
        section_title: str,
        evidence_items: list[dict[str, Any]],
        id_key: str = "evidence_id",
    ) -> list[str]:
        """Like rank_for_section, but returns just the ordered id list
        (unlimited, no marker assignment) -- the shape Stage 2f's RRF fusion
        needs as one of its two ranked lists. Items without an id under
        `id_key` are skipped, since fusion needs a stable identifier."""
        ranked = self.rank_for_section(
            clarified_summary=clarified_summary,
            section_title=section_title,
            evidence_items=evidence_items,
            limit=len(evidence_items) or 1,
        )
        return [item[id_key] for item in ranked if item.get(id_key)]

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

        return score, ";".join(reasons) or "generic_match"

    def _section_terms(self, section_title: str) -> set[str]:
        return self._keywords(section_intent(section_title))

    def keywords(self, text: str) -> set[str]:
        """Public alias — other services score text against the same terms."""
        return self._keywords(text)

    def _keywords(self, text: str) -> set[str]:
        return {
            word
            for word in re.findall(r"[a-zA-Z][a-zA-Z-]+", text.lower())
            if len(word) > 3 and word not in STOPWORDS
        }
