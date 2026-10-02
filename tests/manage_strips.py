"""Scaffold per-strip photo folders and regenerate labels.json from them.

Photo layout (see tasks/todo.md Day 4):

    tests/test_images/<slug>/front-NN.jpg   eval-eligible (brand-name side)
    tests/test_images/<slug>/back-NN.jpg    transcription source, never scored

Usage:
    python -m tests.manage_strips scaffold   # one folder per data/local_dataset.json name
    python -m tests.manage_strips label      # scan folders -> tests/labels.json

'scaffold' creates folders named after the current dataset, so run it again
after replacing the temporary dataset with the real strip data (Day 4).
'label' rebuilds labels.json from whatever front-*.jpg files exist; back photos
and folders that don't match a dataset entry are reported, not guessed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from data.matcher import load_dataset
from tests.labels import REAL_LABELS, TESTS_DIR, is_eval_eligible, slugify

TEST_IMAGES = TESTS_DIR / "test_images"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def scaffold() -> None:
    created = existing = 0
    for entry in load_dataset():
        folder = TEST_IMAGES / slugify(entry["name"])
        if folder.exists():
            existing += 1
        else:
            folder.mkdir(parents=True, exist_ok=True)
            created += 1
            print(f"  created  {folder.relative_to(TESTS_DIR)}")
    print(f"scaffold: {created} created, {existing} already present")


def label() -> None:
    labels: dict[str, str] = {}
    unmatched: list[str] = []
    by_slug = {slugify(entry["name"]): entry["name"] for entry in load_dataset()}

    for folder in sorted(path for path in TEST_IMAGES.iterdir() if path.is_dir()):
        if folder.name.startswith("synth"):
            continue
        medicine = by_slug.get(folder.name)
        if medicine is None:
            unmatched.append(folder.name)
            continue
        for image in sorted(folder.iterdir()):
            if image.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if is_eval_eligible(image.name):
                labels[f"{folder.name}/{image.name}"] = medicine

    REAL_LABELS.write_text(json.dumps(labels, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    backs = sum(1 for folder in TEST_IMAGES.iterdir() if folder.is_dir() for f in folder.iterdir() if f.stem.lower().startswith("back"))
    print(f"label: {len(labels)} front photos labelled -> {REAL_LABELS.name} ({backs} back photos excluded)")
    for name in unmatched:
        print(f"  WARNING: folder '{name}' has no matching dataset entry - ignored")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage per-strip photo folders and labels.")
    parser.add_argument("command", choices=["scaffold", "label"], help="scaffold folders from the dataset, or rebuild labels.json")
    args = parser.parse_args()
    if not TEST_IMAGES.exists():
        sys.exit(f"missing {TEST_IMAGES}")
    scaffold() if args.command == "scaffold" else label()


if __name__ == "__main__":
    main()
