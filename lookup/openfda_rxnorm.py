"""Tier 2 — RxNorm approximate name match, then OpenFDA label fields.

Owner: Person B (see tasks/split.md). Returns the shared response schema on a
hit, or None so the endpoint can fall through to web_search.py. The timeout is
deliberately short: a dead network must never stall the demo.

Flow:
    1. POST OCR text to RxNorm /approximateTerm → best RxCUI candidate
    2. GET OpenFDA /drug/label.json?search=openfda.rxcui:"{rxcui}" → label fields
    3. Map label fields into the shared response schema dict
"""

from __future__ import annotations

import logging
from typing import Any

import requests

__all__ = ["lookup"]

log = logging.getLogger(__name__)

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
DEFAULT_TIMEOUT = 3.0


def _rxcui_from_name(query: str, timeout: float) -> str | None:
    """Resolve a drug name to a RxCUI via RxNorm approximate term search."""
    url = f"{RXNORM_BASE}/approximateTerm.json"
    params = {"term": query, "maxEntries": 1}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        candidates = (
            data.get("approximateGroup", {})
            .get("candidate", [])
        )
        if candidates:
            return candidates[0].get("rxcui")
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        log.debug("RxNorm lookup failed for %r: %s", query, exc)
    return None


def _join(items: list[str] | None, sep: str = "; ") -> str:
    """Join a list of strings, stripping whitespace, or return empty string."""
    if not items:
        return ""
    return sep.join(s.strip() for s in items if s and s.strip())


def _openfda_label(rxcui: str, timeout: float) -> dict[str, Any] | None:
    """Fetch OpenFDA label for the given RxCUI and extract useful fields."""
    params = {
        "search": f'openfda.rxcui:"{rxcui}"',
        "limit": 1,
    }
    try:
        resp = requests.get(OPENFDA_BASE, params=params, timeout=timeout)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        label = results[0]
        openfda = label.get("openfda", {})

        # Extract the most useful brand / generic names
        brand = _join(openfda.get("brand_name", []))
        generic = _join(openfda.get("generic_name", []))

        # Indications / purpose as "uses"
        uses = _join(label.get("indications_and_usage") or label.get("purpose", []))

        # Dosage
        dosage = _join(label.get("dosage_and_administration", []))

        # Side effects / warnings
        side_effects = _join(
            label.get("adverse_reactions")
            or label.get("warnings_and_cautions")
            or label.get("warnings", [])
        )

        return {
            "matched": True,
            "source_tier": "api",
            "name": brand or generic or "",
            "generic_name": generic,
            "uses": uses[:500] if uses else "",
            "dosage": dosage[:500] if dosage else "",
            "side_effects": side_effects[:500] if side_effects else "",
            "confidence": 0.6,  # API match — lower than a local curated hit
        }
    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        log.debug("OpenFDA lookup failed for rxcui %s: %s", rxcui, exc)
    return None


def lookup(query: str, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
    """Resolve `query` through RxNorm -> OpenFDA.

    Returns the shared response schema dict on a successful match, or None so
    the endpoint falls through to the web search tier.  Timeouts and network
    errors return None — the demo must never hang on a dead network.
    """
    if not query or not query.strip():
        return None

    # Use half the timeout budget for each external call
    per_call = timeout / 2

    rxcui = _rxcui_from_name(query, per_call)
    if not rxcui:
        log.debug("No RxCUI found for %r", query)
        return None

    result = _openfda_label(rxcui, per_call)
    if result:
        log.info("OpenFDA match for %r (rxcui=%s): %s", query, rxcui, result.get("name"))
    return result
