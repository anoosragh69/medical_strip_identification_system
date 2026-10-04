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
    5. If the full OCR string yields nothing (garbage tails derail
       approximateTerm), retry from scratch with the focus token — the
       longest ≥6-char alpha run, which is the printed drug name on real
       strips ("Dulcoflex" out of "…Dulcoflex\" Hisaud| TabksiP Sm  Ea
       Eaten So7d…"). All calls share one wall-clock deadline.

Notes from 2026-10-04 probing: the by-rxcui query
(openfda.rxcui:"<id>") returns HTTP 404 for every RxCUI we tried, so
search is by name. A 404 doubles as the final garbage gate for words
openFDA does not index (e.g. India-only brands like "Dulcoflex").
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests
from rapidfuzz import fuzz

__all__ = ["lookup"]

log = logging.getLogger(__name__)

RXNORM_BASE = "https://rxnav.nlm.nih.gov/REST"
OPENFDA_BASE = "https://api.fda.gov/drug/label.json"
# Wall-clock budget for the whole tier (all attempts, all calls).
# Measured latency (2026-10-04, mildly throttled network): RxNorm 1.8-2.3 s,
# OpenFDA 1.1-2.5 s — the focus-retry path (approx → approx → label) needs
# headroom past 6 s; a dead network is cut off at this deadline.
DEFAULT_TIMEOUT = 8.0
# Gap between real matches (≥ 66.7) and junk (≤ 44.4) on measured pairs.
_RELEVANCE_CUTOFF = 55.0
# Smallest budget worth starting a request with.
_MIN_CALL = 0.5


def _left(deadline: float, cap: float) -> float:
    """Seconds left for the next request: per-call cap, bounded by deadline."""
    return min(cap, deadline - time.monotonic())


def _req_timeout(deadline: float, cap: float) -> tuple[float, float]:
    """requests timeout (connect, read) honoring the tier deadline.

    Connect is capped at 2 s so a call that starts just before the deadline
    can't run to 2× the remaining budget, while still tolerating a slow
    DNS/TLS handshake. (A 1 s cap proved too tight: the Cyclosporine test
    failed both attempts on a connect that took just over 1 s.)
    """
    left = _left(deadline, cap)
    return (min(2.0, left), left)


def _focus_token(query: str) -> str | None:
    """Longest ≥6-char alpha run — the printed drug name on real strips."""
    runs = re.findall(r"[A-Za-z]{6,}", query)
    return max(runs, key=len) if runs else None


def _canonical_name(
    query: str, deadline: float, cap: float, *, skip_properties_if_named: bool = False
) -> tuple[str, str] | None:
    """Best (rxcui, RxNorm name) for the query, or None.

    Candidates come back in score order from /approximateTerm; some carry no
    name (seen on real queries like "Paracetamol 650"), so fall back to the
    preferred name from /rxcui/{id}/properties.json for the top RxCUI. Every
    name must clear the relevance gate against the OCR query.

    skip_properties_if_named: when a focus-token attempt follows anyway and
    approx already returned named candidates (that merely failed the gate on
    the noisy full text), skip the ~1.5 s properties call — the focus retry
    re-approximates with cleaner text instead. All-unnamed candidate lists
    still get the fallback: that is the Paracetamol-650 case where properties
    is the only source of a name.
    """
    try:
        resp = requests.get(
            f"{RXNORM_BASE}/approximateTerm.json",
            params={"term": query, "maxEntries": 5},
            timeout=_req_timeout(deadline, cap),
        )
        resp.raise_for_status()
        candidates = resp.json().get("approximateGroup", {}).get("candidate", []) or []
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        log.debug("RxNorm approximateTerm failed for %r: %s", query, exc)
        return None

    def relevant(name: str) -> bool:
        return fuzz.partial_ratio(name.lower(), query.lower()) >= _RELEVANCE_CUTOFF

    first_rxcui = None
    named_seen = False
    for candidate in candidates:
        rxcui = str(candidate.get("rxcui") or "").strip()
        name = str(candidate.get("name") or "").strip()
        if rxcui and not first_rxcui:
            first_rxcui = rxcui
        if rxcui and name:
            named_seen = True
            if relevant(name):
                return rxcui, name
            log.debug("RxNorm candidate %r not relevant to %r — scanning on", name, query)

    if not first_rxcui or _left(deadline, cap) < _MIN_CALL:
        return None
    if skip_properties_if_named and named_seen:
        return None

    try:
        resp = requests.get(
            f"{RXNORM_BASE}/rxcui/{first_rxcui}/properties.json",
            timeout=_req_timeout(deadline, cap),
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


def _openfda_label(drug_word: str, deadline: float, cap: float) -> dict[str, Any] | None:
    """Fetch the OpenFDA label by generic OR brand name and extract fields."""
    params = {
        "search": f'openfda.generic_name:"{drug_word}" OR openfda.brand_name:"{drug_word}"',
        "limit": 1,
    }
    if _left(deadline, cap) < _MIN_CALL:
        return None
    try:
        resp = requests.get(OPENFDA_BASE, params=params, timeout=_req_timeout(deadline, cap))
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
    """Resolve `query` through RxNorm approximate match -> OpenFDA label.

    Tries the full OCR text first, then the focus token (longest ≥6-char
    alpha run) when garbage tails derail approximateTerm. Returns the shared
    response schema dict on a successful match, or None so the endpoint falls
    through to the web-search tier. All calls share one wall-clock deadline —
    the demo must never hang on a dead network.
    """
    if not query or not query.strip():
        return None

    deadline = time.monotonic() + timeout
    cap = timeout / 2  # per-call cap; the deadline does the real limiting
    attempts = list(dict.fromkeys(a for a in (query, _focus_token(query)) if a))
    tried_words: set[str] = set()

    for i, attempt_query in enumerate(attempts):
        if _left(deadline, cap) < _MIN_CALL:
            break
        match = _canonical_name(
            attempt_query, deadline, cap,
            skip_properties_if_named=(i < len(attempts) - 1),
        )
        if not match:
            log.debug("No RxNorm candidate for %r", attempt_query)
            continue
        canonical = match[1]

        word = _drug_word(canonical)
        if not word or word.lower() in tried_words:
            log.debug("No new searchable word in RxNorm name %r for %r", canonical, attempt_query)
            continue
        tried_words.add(word.lower())

        result = _openfda_label(word, deadline, cap)
        if result:
            log.info("OpenFDA match for %r (rxnorm=%r): %s", query, canonical, result.get("name"))
            return result
    return None
