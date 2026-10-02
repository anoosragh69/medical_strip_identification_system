"""Label loading and path conventions for the test set.

Two label files exist:
- synthetic_labels.json - written by tests/gen_synthetic.py (owns its file)
- labels.json           - written by tests/manage_strips.py, real strip photos

load_labels() merges both, so eval sees the whole set. Photo layout for real
strips: tests/test_images/<slug>/front-NN.jpg (eval-eligible) and back-NN.jpg
(transcription source only - excluded by is_eval_eligible).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SYNTHETIC_LABELS = TESTS_DIR / "synthetic_labels.json"
REAL_LABELS = TESTS_DIR / "labels.json"


def load_labels() -> dict[str, str]:
    """Merged label map: relative image path -> expected medicine name."""
    merged: dict[str, str] = {}
    for path in (SYNTHETIC_LABELS, REAL_LABELS):
        if path.exists():
            merged.update(json.loads(path.read_text(encoding="utf-8")))
    return merged


def is_eval_eligible(relative_path: str) -> bool:
    """Back-panel photos are transcription sources, not accuracy targets.

    Back panels don't contain the brand name, so scoring them would tank the
    accuracy number without testing anything the pipeline does.
    """
    stem = Path(relative_path).stem.lower()
    return not stem.startswith("back")


def slugify(name: str) -> str:
    """Folder-safe slug of a dataset name: 'DOLO 650' -> 'dolo-650'."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError(f"name has no folder-safe characters: {name!r}")
    return slug
