"""Tier 2 — RxNorm approximate name match, then OpenFDA label fields.

Owner: Person B (see tasks/split.md). Returns the shared response schema on a
hit, or None so the endpoint can fall through to web_search.py. The timeout is
deliberately short: a dead network must never stall the demo.
"""

from __future__ import annotations

__all__ = ["lookup"]

DEFAULT_TIMEOUT = 3.0


def lookup(query: str, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
    """Resolve `query` through RxNorm -> OpenFDA.

    Raises nothing on network failure: timeouts and errors return None.
    """
    raise NotImplementedError("Person B: implement in Day 4")
