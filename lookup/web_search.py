"""Tier 3 — web search fallback, best-effort only.

Owner: Person B (see tasks/split.md). Top-K DuckDuckGo snippets, then a
keyword-frequency vote over candidate drug names. Degrades to None when the
network is unavailable; never load-bearing for the demo.

Flow:
    1. Search DuckDuckGo for the OCR text + " medicine strip tablet"
    2. Extract candidate drug names from the top-K snippet titles+bodies
    3. Vote by frequency — the most-mentioned plausible drug name wins
    4. Return the shared response schema with best-effort fields
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter

__all__ = ["search"]

log = logging.getLogger(__name__)

DEFAULT_TOP_K = 5

# Common filler words that are never drug names
_STOP_WORDS = frozenset(
    "the a an of in for and or is to it by on at with from this that be as are "
    "was were has have had do does did will would can could may might shall should "
    "mg ml tab tablet capsule strip medicine drug use uses side effects dosage "
    "price buy online order review reviews information about how what when where "
    "which who why not no yes all each every any some most".split()
)

# A plausible drug name: at least 3 chars, starts with a letter, no excessive digits
_NAME_PATTERN = re.compile(r"\b([A-Z][a-z]{2,}(?:\s?[A-Z][a-z]{2,})?)\b")


def _extract_candidates(text: str) -> list[str]:
    """Pull plausible drug names from a search snippet."""
    candidates = []
    for match in _NAME_PATTERN.finditer(text):
        word = match.group(1).strip()
        if len(word) < 3:
            continue
        lowered = word.lower()
        # Reject single stopwords and bigrams made only of stopwords
        # ("Side Effects" appears in nearly every medicine title).
        if lowered in _STOP_WORDS or all(tok in _STOP_WORDS for tok in lowered.split()):
            continue
        candidates.append(word)
    return candidates


def search(query: str, top_k: int = DEFAULT_TOP_K) -> dict | None:
    """Return the shared response schema for a voted web result, else None.

    Uses ``ddgs`` (the renamed ``duckduckgo_search`` package; the old import
    is kept as a fallback) to fetch snippets, then votes on the most
    frequently mentioned drug name across them. Returns None on any failure
    so the endpoint falls through to the clean not-found response.
    """
    if not query or not query.strip():
        return None

    try:
        from ddgs import DDGS  # current package name (duckduckgo_search was renamed)
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            log.warning("ddgs not installed — tier 3 disabled")
            return None

    search_query = f"{query} medicine strip tablet uses dosage"

    results: list[dict] = []
    for attempt in range(2):  # backends rate-limit intermittently; retry empty once
        if attempt:
            time.sleep(0.5)
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=top_k))
        except Exception as exc:  # noqa: BLE001
            log.debug("DuckDuckGo search failed for %r: %s", query, exc)
            return None
        if results:
            break

    if not results:
        return None

    # Collect candidate drug names from all snippets
    vote_counter: Counter[str] = Counter()
    snippet_texts: list[str] = []

    for r in results:
        title = r.get("title", "")
        body = r.get("body", "")
        combined = f"{title} {body}"
        snippet_texts.append(combined)
        for candidate in _extract_candidates(combined):
            vote_counter[candidate.title()] += 1

    if not vote_counter:
        return None

    # The winner is the most-mentioned plausible drug name
    winner, count = vote_counter.most_common(1)[0]

    # Require at least 2 mentions across snippets for any confidence
    if count < 2:
        log.debug("No strong consensus from web search for %r (best: %s x%d)", query, winner, count)
        return None

    # Try to extract uses/dosage from the snippets mentioning the winner
    uses_snippets = []
    for text in snippet_texts:
        if winner.lower() in text.lower():
            uses_snippets.append(text)

    uses_text = "; ".join(uses_snippets)[:500] if uses_snippets else ""

    log.info("Web search vote for %r: %s (count=%d)", query, winner, count)

    return {
        "matched": True,
        "source_tier": "web",
        "name": winner,
        "generic_name": "",
        "uses": uses_text,
        "dosage": "",
        "side_effects": "",
        "confidence": min(0.3 + (count - 2) * 0.05, 0.5),  # never very high — it's best-effort
    }
