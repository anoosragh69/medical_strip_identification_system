"""Tier 3 — web search fallback, best-effort only.

Owner: Person B (see tasks/split.md). Top-K DuckDuckGo snippets, then a
keyword-frequency vote over candidate drug names. Degrades to None when the
network is unavailable; never load-bearing for the demo.
"""

from __future__ import annotations

__all__ = ["search"]

DEFAULT_TOP_K = 5


def search(query: str, top_k: int = DEFAULT_TOP_K) -> dict | None:
    """Return the shared response schema for a voted web result, else None."""
    raise NotImplementedError("Person B: implement in Day 4")
