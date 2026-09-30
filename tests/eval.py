"""Accuracy and latency scoring over the labeled test set.

Owner: Person A (see tasks/split.md). Produces the numbers for the report:
identification accuracy per tier, OCR error rate, and mean latency per stage.

Usage (once implemented):
    python -m tests.eval --images tests/test_images --labels tests/labels.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

TEST_IMAGES = Path(__file__).resolve().parent / "test_images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score the identification pipeline against the labeled set.")
    parser.add_argument("--images", type=Path, default=TEST_IMAGES, help="directory of labeled strip photos")
    parser.add_argument("--labels", type=Path, default=None, help="JSON file mapping image name -> expected medicine")
    parser.add_argument("--threshold", type=float, default=80.0, help="fuzzy match cutoff used for this run")
    parser.add_argument("--output", type=Path, default=None, help="write the metrics report here as JSON")
    return parser.parse_args()


def run(images: Path, labels: Path | None, threshold: float) -> dict:
    """Return {accuracy, ocr_error_rate, tier_breakdown, latency_ms}."""
    raise NotImplementedError("Person A: implement in Day 7")


def main() -> None:
    args = parse_args()
    report = run(args.images, args.labels, args.threshold)
    for key, value in report.items():
        print(f"{key:>18}: {value}")


if __name__ == "__main__":
    main()
