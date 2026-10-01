"""Fuzzy matching of OCR output against the curated local dataset.

Owner: Person A (see tasks/split.md). This is the primary, always-on tier -
it must work with zero internet, so it resolves first in server/main.py.

Matching strategy: token_set_ratio handles the common case where the OCR text
contains the strip name mixed with other printed text ("AZEE 500 Azithromycin
Tablets IP" vs dataset name "AZEE 500"); WRatio is a second opinion tuned to
catch one-token order flips ("500 Azee"). The higher of the two wins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

__all__ = ["MatchResult", "DEFAULT_DATASET", "load_dataset", "match_local"]

DEFAULT_DATASET = Path(__file__).resolve().parent / "local_dataset.json"
DEFAULT_CUTOFF = 80.0


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

    best_name, best_score, best_record = "", 0.0, None
    for entry in dataset:
        name = entry.get("name", "")
        if not name:
            continue
        score = score_pair(text, name)
        if score > best_score:
            best_name, best_score, best_record = name, score, entry

    if best_score < score_cutoff:
        return None
    return MatchResult(matched=True, name=best_name, score=round(best_score, 2), record=best_record)
