"""Fuzzy matching of OCR output against the curated local dataset.

Owner: Person A (see tasks/split.md). This is the primary, always-on tier —
it must work with zero internet, so it resolves first in server/main.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

__all__ = ["MatchResult", "DEFAULT_DATASET", "load_dataset", "match_local"]

DEFAULT_DATASET = Path(__file__).resolve().parent / "local_dataset.json"


@dataclass
class MatchResult:
    matched: bool
    name: str
    score: float  # 0-100 fuzzy score


def load_dataset(path: Path = DEFAULT_DATASET) -> list[dict]:
    """Read the curated medicine records from disk."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def match_local(text: str, score_cutoff: float = 80.0, dataset: list[dict] | None = None) -> MatchResult | None:
    """Best fuzzy score over the dataset names; None below the cutoff.

    Entries look like:
    {"name": "", "generic_name": "", "uses": "", "dosage": "", "side_effects": ""}
    """
    raise NotImplementedError("Person A: implement in Day 3")
