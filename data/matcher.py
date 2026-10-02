"""Fuzzy matching of OCR output against the curated local dataset.

Owner: Person A (see tasks/split.md). This is the primary, always-on tier -
it must work with zero internet, so it resolves first in server/main.py.

Matching strategy: token_set_ratio handles the common case where the OCR text
contains the strip name mixed with other printed text ("AZEE 500 Azithromycin
Tablets IP" vs dataset name "AZEE 500"); WRatio is a second opinion tuned to
catch one-token order flips ("500 Azee"). The higher of the two wins.

Guard: WRatio's partial-ratio component can inflate scores for unrelated names
(an unknown "TYLENOL 500 ..." strip scored 85.5 against "AZEE 500"), so a name
qualifies only if every token of it appears somewhere in the OCR text - or the
fuzzy score is near-perfect (>=95), which keeps the door open for a single
mangled character in an otherwise correct read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

__all__ = ["MatchResult", "DEFAULT_DATASET", "load_dataset", "match_local"]

DEFAULT_DATASET = Path(__file__).resolve().parent / "local_dataset.json"
DEFAULT_CUTOFF = 80.0
NEAR_PERFECT_SCORE = 95.0  # bypasses the token-coverage guard for single-char OCR mangling


@dataclass
class MatchResult:
    matched: bool
    name: str
    score: float  # 0-100 fuzzy score
    record: dict | None = field(default=None)  # the matched dataset entry, for the response


def load_dataset(path: Path = DEFAULT_DATASET) -> list[dict]:
    """Read the curated medicine records from disk."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _normalize(text: str) -> str:
    """Case-fold and squash punctuation - rapidfuzz scorers are case-sensitive."""
    return " ".join("".join(char if char.isalnum() else " " for char in text.upper()).split())


def score_pair(ocr_text: str, name: str) -> float:
    """Score one OCR string against one dataset name."""
    ocr_text, name = _normalize(ocr_text), _normalize(name)
    return max(
        fuzz.token_set_ratio(ocr_text, name),
        fuzz.WRatio(ocr_text, name),
    )


def _tokens(text: str) -> list[str]:
    """Meaningful name tokens (>=2 chars) from normalised text."""
    return [token for token in _normalize(text).split() if len(token) >= 2]


def _fully_covered(name: str, ocr_text: str) -> bool:
    """True when every token of the dataset name appears in the OCR text."""
    return all(token in ocr_text for token in _tokens(name))


def match_local(
    text: str,
    score_cutoff: float = DEFAULT_CUTOFF,
    dataset: list[dict] | None = None,
) -> MatchResult | None:
    """Best fuzzy score over the dataset names; None below the cutoff.

    Entries look like:
    {"name": "", "generic_name": "", "uses": "", "dosage": "", "side_effects": ""}
    """
    if dataset is None:
        dataset = load_dataset()
    if not text.strip() or not dataset:
        return None

    normalised_text = _normalize(text)
    best_name, best_score, best_record = "", 0.0, None
    for entry in dataset:
        name = entry.get("name", "")
        if not name:
            continue
        score = score_pair(text, name)
        if score < score_cutoff:
            continue
        if score < NEAR_PERFECT_SCORE and not _fully_covered(name, normalised_text):
            continue
        if score > best_score:
            best_name, best_score, best_record = name, score, entry

    if not best_record:
        return None
    return MatchResult(matched=True, name=best_name, score=round(best_score, 2), record=best_record)
