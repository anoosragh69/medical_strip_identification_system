"""Tier 2 — RxNorm approximate name match, then OpenFDA label fields.

Owner: Person B (see tasks/split.md). Returns the shared response schema on a
hit, or None so the endpoint can fall through to web_search.py. The timeout is
deliberately short: a dead network must never stall the demo.

Flow:
    1. GET RxNorm /approximateTerm → best candidate for the OCR text
    2. Use its canonical name ("ibuprofen 400 MG [Brufen]" → "ibuprofen").
       Some queries (e.g. "Paracetamol 650") match only unnamed candidates,
       so when the name is missing, GET /rxcui/{id}/properties.json for the
       preferred RxNorm name instead — that is how INN/USAN pairs resolve
       ("paracetamol" → "acetaminophen", which openFDA does index).
    3. GET OpenFDA /drug/label.json?search=openfda.generic_name:"<word>"
       → label fields, then map them into the shared response schema.

Step 3 searches by generic name because the by-rxcui query
(openfda.rxcui:"<id>") returns HTTP 404 for every RxCUI we tried — verified
against both api.fda.gov and a direct requests call on 2026-10-04. The
generic-name query returns 200 in ~1.0-1.3 s for real drugs and 404 for
non-drug words, which doubles as the garbage gate: OCR noise that slips
through approximateTerm dies here.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

__all__ = ["lookup"]

log = logging.getLogger(__name__)

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
# 2 s per call, 6 s ceiling. Measured on the demo network: RxNorm calls
# 1.1-1.9 s, OpenFDA 1.0-1.3 s, so the old 1.5 s split timed out good calls.
DEFAULT_TIMEOUT = 6.0


def _canonical_name(query: str, timeout: float) -> tuple[str, str] | None:
    """Best (rxcui, RxNorm name) for the query, or None.

    Candidates come back in score order from /approximateTerm; some carry no
    name (seen on real queries like "Paracetamol 650"), so fall back to the
    preferred name from /rxcui/{id}/properties.json for the top RxCUI.
    """
    try:
        resp = requests.get(
            f"{RXNORM_BASE}/approximateTerm.json",
            params={"term": query, "maxEntries": 5},
            timeout=timeout,
        )
        resp.raise_for_status()
        candidates = resp.json().get("approximateGroup", {}).get("candidate", []) or []
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        log.debug("RxNorm approximateTerm failed for %r: %s", query, exc)
        return None

    first_rxcui = None
    for candidate in candidates:
        rxcui = str(candidate.get("rxcui") or "").strip()
        name = str(candidate.get("name") or "").strip()
        if rxcui and not first_rxcui:
            first_rxcui = rxcui
        if rxcui and name:
            return rxcui, name

    if not first_rxcui:
        return None

    try:
        resp = requests.get(
            f"{RXNORM_BASE}/rxcui/{first_rxcui}/properties.json",
            timeout=timeout,
        )
        resp.raise_for_status()
        name = str(resp.json().get("properties", {}).get("name") or "").strip()
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        log.debug("RxNorm properties failed for rxcui %s: %s", first_rxcui, exc)
        return None
    return (first_rxcui, name) if name else None


def _drug_word(canonical_name: str) -> str | None:
    """Leading alpha run of the canonical name: 'ibuprofen 400 MG' -> 'ibuprofen'."""
    match = re.search(r"[A-Za-z]{3,}", canonical_name)
    return match.group(0) if match else None


def _join(items: list[str] | None, sep: str = "; ") -> str:
    """Join a list of strings, stripping whitespace, or return empty string."""
    if not items:
        return ""
    return sep.join(s.strip() for s in items if s and s.strip())


def _openfda_label(drug_word: str, timeout: float) -> dict[str, Any] | None:
    """Fetch the OpenFDA label for a generic drug name and extract fields."""
    params = {
        "search": f'openfda.generic_name:"{drug_word}"',
        "limit": 1,
    }
    try:
        resp = requests.get(OPENFDA_BASE, params=params, timeout=timeout)
        if resp.status_code == 404:
            # No label for this word — expected for OCR garbage and for
            # ingredients openFDA does not index.
            return None
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
            "name": brand or generic or drug_word,
            "generic_name": generic or drug_word,
            "uses": uses[:500] if uses else "",
            "dosage": dosage[:500] if dosage else "",
            "side_effects": side_effects[:500] if side_effects else "",
            "confidence": 0.6,  # API match — lower than a local curated hit
        }
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        log.debug("OpenFDA lookup failed for %r: %s", drug_word, exc)
    return None


def lookup(query: str, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
    """Resolve `query` through RxNorm approximate match -> OpenFDA by generic name.

    Returns the shared response schema dict on a successful match, or None so
    the endpoint falls through to the web-search tier. Timeouts and network
    errors return None — the demo must never hang on a dead network.
    """
    if not query or not query.strip():
        return None

    # Use half the timeout budget for each external call
    per_call = timeout / 2

    match = _canonical_name(query, per_call)
    if not match:
        log.debug("No RxNorm candidate for %r", query)
        return None
    canonical = match[1]

    word = _drug_word(canonical)
    if not word:
        log.debug("No searchable word in RxNorm name %r for %r", canonical, query)
        return None

    result = _openfda_label(word, per_call)
    if result:
        log.info("OpenFDA match for %r (rxnorm=%r): %s", query, canonical, result.get("name"))
    return result
