"""Tier 3 — web search fallback, best-effort only.

Owner: Person B (see tasks/split.md). Top-K snippets via ``ddgs``, then a
grounded vote over candidate drug names. Degrades to None when the network
is unavailable; never load-bearing for the demo.

Flow:
    1. Query variants under one deadline: full OCR text + suffix, then the
       focus token (longest ≥6-char alpha run — skips gibberish tails that
       derail engines), then the auto backend chain as last resort
    2. Extract candidate drug names from the top-K snippet titles+bodies
    3. Vote among candidates grounded in the OCR text: exact query tokens
       first (the strip printed that name), then mention count (≥2 = consensus)
    4. Return the shared response schema with best-effort fields
"""

from __future__ import annotations

import logging
import re
import threading
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
# Wall-clock budget for the whole tier (all variants, all backends).
_SEARCH_DEADLINE_S = 10.0
_SUFFIX = "medicine strip tablet uses dosage"

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


def _focus_token(query: str) -> str | None:
    """Longest ≥6-char alpha run — the printed drug name on real strips."""
    runs = re.findall(r"[A-Za-z]{6,}", query)
    return max(runs, key=len) if runs else None


def _fetch(search_query: str, top_k: int, backend: str, budget_s: float) -> list[dict]:
    """Top-K snippets, waiting at most budget_s.

    ddgs' own timeout is per engine and its auto chain tries several, so a
    single call can outlast the tier deadline (measured 15.9 s total while
    engines were rate-limited). Run it on a daemon thread and stop waiting at
    the budget instead — the demo must never hang on a slow backend.
    """
    box: dict[str, list[dict]] = {}

    def run() -> None:
        try:
            from ddgs import DDGS  # current package name (duckduckgo_search was renamed)

            with DDGS(timeout=max(2, min(4, int(budget_s)))) as ddgs:
                box["r"] = ddgs.text(search_query, max_results=top_k, backend=backend)
        except Exception as exc:  # noqa: BLE001 - empty result set is raised too
            log.debug("DuckDuckGo search (backend=%s) failed: %s", backend, exc)
            box["r"] = []

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(budget_s)
    if thread.is_alive():
        log.debug("DuckDuckGo search (backend=%s) exceeded %.1fs budget", backend, budget_s)
        return []
    return box.get("r", [])


def _vote(results: list[dict], query_tokens: list[str]) -> dict | None:
    """Build the shared-schema response from the best OCR-grounded candidate.

    Grounding keeps condition/platform words ("Constipation", "DailyMed")
    from winning when engines return generic pages; exact query tokens rank
    above raw counts because the strip printed that name. Fuzzy match so
    minor OCR typos still pass.
    """
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

    def grounded(name: str) -> bool:
        name_l = name.lower()
        return any(fuzz.partial_ratio(tok, name_l) >= 85 for tok in query_tokens)

    ranked = [
        (count, name)
        for name, count in vote_counter.items()
        if grounded(name) and count >= 2  # >=2 mentions = real consensus
    ]
    if not ranked:
        log.debug("No grounded web candidate (top: %s)", vote_counter.most_common(3))
        return None
    # Exact query tokens win first (the strip printed that name), then vote
    # count; ties go to shorter names
    ranked.sort(
        key=lambda item: (item[1].lower() in query_tokens, item[0], -len(item[1])),
        reverse=True,
    )
    count, winner = ranked[0]

    # Try to extract uses/dosage from the snippets mentioning the winner
    uses_snippets = [text for text in snippet_texts if winner.lower() in text.lower()]
    uses_text = "; ".join(uses_snippets)[:500] if uses_snippets else ""

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


def search(query: str, top_k: int = DEFAULT_TOP_K) -> dict | None:
    """Return the shared response schema for a voted web result, else None.

    Uses ``ddgs`` (the renamed ``duckduckgo_search`` package; the old import
    is kept as a fallback). Query variants and backends are tried under one
    wall-clock deadline; an exact-token vote returns immediately, a fuzzy
    one is kept as fallback while better variants are attempted. Returns
    None on any failure so the endpoint falls through to the clean
    not-found response.
    """
    if not query or not query.strip():
        return None

    try:
        import ddgs  # noqa: F401 - current package name (duckduckgo_search was renamed)
    except ImportError:
        try:
            import duckduckgo_search  # noqa: F401
        except ImportError:
            log.warning("ddgs not installed — tier 3 disabled")
            return None

    query_tokens = [tok for tok in re.findall(r"[a-z]+", query.lower()) if len(tok) >= 4]

    # Variant order: full OCR text first (clean queries resolve here), then
    # the focus token (gibberish tails derail engines), then the auto backend
    # chain on the focus variant as last resort. Pinned backends are the
    # fast, consistently-responsive ones.
    variants = list(dict.fromkeys(v for v in (query, _focus_token(query)) if v))
    plan: list[tuple[str, str]] = [
        (f"{variant} {_SUFFIX}", "mojeek,yahoo,startpage") for variant in variants
    ]
    plan.append((f"{variants[-1]} {_SUFFIX}", "auto"))

    deadline = time.monotonic() + _SEARCH_DEADLINE_S
    fallback: dict | None = None

    for i, (search_query, backend) in enumerate(plan):
        left = deadline - time.monotonic()
        if left < 1.5:
            break
        if i:
            time.sleep(0.3)
        results = _fetch(search_query, top_k, backend, deadline - time.monotonic())
        if not results:
            continue

        response = _vote(results, query_tokens)
        if response is None:
            continue
        if response["name"].lower() in query_tokens:
            log.info("Web search vote for %r: %s (exact)", query, response["name"])
            return response
        if fallback is None:
            fallback = response  # fuzzy-grounded: keep looking for an exact one

    if fallback:
        log.info("Web search vote for %r: %s (fuzzy fallback)", query, fallback["name"])
    return fallback
