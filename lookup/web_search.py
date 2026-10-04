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

from rapidfuzz import fuzz

__all__ = ["search"]

log = logging.getLogger(__name__)

# ddgs logs per-engine errors at INFO and drags third-party HTTP/DNS clients
# along; keep them at WARNING so the server log stays readable.
for _lib in ("ddgs", "primp", "hickory", "h2", "cookie_store"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

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
    is kept as a fallback) to fetch snippets, then votes among candidate drug
    names that are grounded in the OCR text (exact token first, then votes).
    Returns None on any failure so the endpoint falls through to the clean
    not-found response.
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

    # First pass pins the fast, consistently-responsive engines; if they come
    # back empty (they rate-limit intermittently - ddgs raises "No results
    # found."), retry once against the full auto backend chain. A slow first
    # pass means the network itself is down, so skip the second attempt
    # instead of stacking another 8+ s of timeouts.
    results: list[dict] = []
    started = time.monotonic()
    for attempt, backend in enumerate(("mojeek,yahoo,startpage", "auto")):
        if attempt:
            if time.monotonic() - started >= 5.0:
                break
            time.sleep(0.5)
        try:
            with DDGS(timeout=4) as ddgs:
                results = ddgs.text(search_query, max_results=top_k, backend=backend)
        except Exception as exc:  # noqa: BLE001 - empty result set is raised too
            log.debug("DuckDuckGo search (backend=%s) failed for %r: %s", backend, query, exc)
            results = []
            continue
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

    # Ground candidates in the OCR text first, then vote among them: engines
    # return generic drug pages even for noisy queries, and their condition or
    # platform words ("Constipation", "DailyMed") can out-vote the real
    # product name. Fuzzy match so minor OCR typos still pass.
    query_tokens = [tok for tok in re.findall(r"[a-z]+", query.lower()) if len(tok) >= 4]

    def grounded(name: str) -> bool:
        name_l = name.lower()
        return any(fuzz.partial_ratio(tok, name_l) >= 85 for tok in query_tokens)

    ranked = [
        (count, name)
        for name, count in vote_counter.items()
        if grounded(name) and count >= 2  # >=2 mentions = real consensus
    ]
    if not ranked:
        log.debug("No grounded web candidate for %r (top: %s)", query, vote_counter.most_common(3))
        return None
    # Exact query tokens win first (the strip printed that name), then vote
    # count; ties go to shorter names
    ranked.sort(
        key=lambda item: (item[1].lower() in query_tokens, item[0], -len(item[1])),
        reverse=True,
    )
    count, winner = ranked[0]

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
