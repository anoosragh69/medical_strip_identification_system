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
    3. Relevance gate: the canonical name must fuzzy-match the OCR text
       (partial_ratio ≥ 55). Noisy OCR can match junk RxNorm products
       ("ASC-JM-17" scored 44 against a real strip's text; real matches
       measure ≥ 66), and rejecting here skips a pointless OpenFDA call.
    4. GET OpenFDA /drug/label.json?search=openfda.generic_name:"<word>"
       OR openfda.brand_name:"<word>" → label fields, mapped into the
       shared response schema. The OR covers brand-word canonical names
       ("Dulcolax" hits only via brand_name).

Notes from 2026-10-04 probing: the by-rxcui query
(openfda.rxcui:"<id>") returns HTTP 404 for every RxCUI we tried, so
search is by name. A 404 doubles as the final garbage gate for words
openFDA does not index (e.g. India-only brands like "Dulcoflex").
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests
from rapidfuzz import fuzz

__all__ = ["lookup"]

log = logging.getLogger(__name__)

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
# 2 s per call, 3 sequential calls, 6 s ceiling. Measured on the demo
# network: RxNorm calls 1.1-1.9 s, OpenFDA 1.0-1.3 s; the old 1.5 s split
# timed out good calls, and dividing by 2 left a 9 s worst case.
DEFAULT_TIMEOUT = 6.0
# Gap between real matches (≥ 66.7) and junk (≤ 44.4) on measured pairs.
_RELEVANCE_CUTOFF = 55.0


def _canonical_name(query: str, timeout: float) -> tuple[str, str] | None:
    """Best (rxcui, RxNorm name) for the query, or None.

    Candidates come back in score order from /approximateTerm; some carry no
    name (seen on real queries like "Paracetamol 650"), so fall back to the
    preferred name from /rxcui/{id}/properties.json for the top RxCUI. Every
    name must clear the relevance gate against the OCR query.
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

    def relevant(name: str) -> bool:
        return fuzz.partial_ratio(name.lower(), query.lower()) >= _RELEVANCE_CUTOFF

    first_rxcui = None
    for candidate in candidates:
        rxcui = str(candidate.get("rxcui") or "").strip()
        name = str(candidate.get("name") or "").strip()
        if rxcui and not first_rxcui:
            first_rxcui = rxcui
        if rxcui and name:
            if relevant(name):
                return rxcui, name
            log.debug("RxNorm candidate %r not relevant to %r — scanning on", name, query)

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
    if name and not relevant(name):
        log.debug("RxNorm properties name %r not relevant to %r", name, query)
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
    """Fetch the OpenFDA label by generic OR brand name and extract fields."""
    params = {
        "search": f'openfda.generic_name:"{drug_word}" OR openfda.brand_name:"{drug_word}"',
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

    # Third of the timeout budget for each of the three sequential calls
    per_call = timeout / 3

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
