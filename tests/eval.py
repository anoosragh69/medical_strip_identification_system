"""Accuracy and latency scoring over the labeled test set.

Owner: Person A (see tasks/split.md). Produces the numbers for the report:
identification accuracy per tier, OCR error rate, and mean latency per stage.

Scoring rules:
- Only eval-eligible labels are scored (back-NN.jpg is a transcription source,
  never an accuracy target - see tests/labels.py).
- A prediction is correct when the local tier matched AND the matched dataset
  name equals the expected name (normalised comparison).
- OCR error rate counts images where the OCR text missed tokens of the
  expected name - separates "OCR never read it" from "matcher never found it".
- Only the local tier runs here; tiers 2/3 need network and stay out of the
  offline harness. Unresolved images are what tier 2/3 would receive.

Usage:
    python -m tests.eval                       # merged synthetic + real labels
    python -m tests.eval --labels tests/labels.json --output report.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2

from data.matcher import _fully_covered, _normalize, _tokens, match_local
from tests.labels import is_eval_eligible, load_labels

TEST_IMAGES = Path(__file__).resolve().parent / "test_images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score the identification pipeline against the labeled set.")
    parser.add_argument("--images", type=Path, default=TEST_IMAGES, help="directory of labeled strip photos")
    parser.add_argument("--labels", type=Path, default=None, help="JSON file mapping image name -> expected medicine")
    parser.add_argument("--threshold", type=float, default=80.0, help="fuzzy match cutoff used for this run")
    parser.add_argument("--dataset", type=Path, default=None, help="medicine records to match against (default: data/local_dataset.json); use tests/synthetic_dataset.json with --labels tests/synthetic_labels.json")
    parser.add_argument("--output", type=Path, default=None, help="write the metrics report here as JSON")
    return parser.parse_args()


def _labels_for(labels: Path | None) -> dict[str, str]:
    if labels is None:
        return load_labels()
    return json.loads(labels.read_text(encoding="utf-8"))


def _mean(samples: list[float]) -> float:
    return round(sum(samples) / len(samples), 1) if samples else 0.0


def run(images: Path, labels: Path | None, threshold: float, dataset: Path | None = None) -> dict:
    """Return {accuracy, ocr_error_rate, tier_breakdown, latency_ms}."""
    from cv.ocr import read_text_adaptive  # lazy: EasyOCR weights load on first use
    from cv.preprocess import preprocess

    records = json.loads(dataset.read_text(encoding="utf-8")) if dataset else None
    label_map = _labels_for(labels)
    entries: list[tuple[str, Path, str]] = []
    skipped_missing = 0
    skipped_ineligible = 0

    for key, expected in sorted(label_map.items()):
        path = images / key
        if not path.exists():
            skipped_missing += 1
            continue
        if not is_eval_eligible(key):
            skipped_ineligible += 1
            continue
        entries.append((key, path, expected))

    correct = wrong = missed = ocr_errors = 0
    failures: list[dict] = []
    preprocess_ms: list[float] = []
    ocr_ms: list[float] = []
    match_ms: list[float] = []
    total_ms: list[float] = []

    for key, path, expected in entries:
        image = cv2.imread(str(path))
        if image is None:
            failures.append({"image": key, "expected": expected, "error": "unreadable image"})
            wrong += 1
            continue

        started = time.perf_counter()
        preprocessed = preprocess(image)
        preprocess_ms.append((time.perf_counter() - started) * 1000)

        ocr = read_text_adaptive(image)  # preprocesses internally, as /upload does
        ocr_ms.append(ocr.elapsed_ms)

        started = time.perf_counter()
        match = match_local(ocr.text, score_cutoff=threshold, dataset=records)
        match_ms.append((time.perf_counter() - started) * 1000)
        total_ms.append(preprocess_ms[-1] + ocr_ms[-1] + match_ms[-1])

        expected_norm = _normalize(expected)
        if not _fully_covered(expected_norm, _normalize(ocr.text)):
            ocr_errors += 1

        if match is None:
            missed += 1
            failures.append(
                {"image": key, "expected": expected, "got": None, "ocr": ocr.text[:120]}
            )
        elif _normalize(match.name) == expected_norm:
            correct += 1
        else:
            wrong += 1
            failures.append(
                {"image": key, "expected": expected, "got": match.name, "score": match.score, "ocr": ocr.text[:120]}
            )

    scored = len(entries)
    return {
        "images_scored": scored,
        "images_skipped_missing": skipped_missing,
        "images_skipped_ineligible": skipped_ineligible,
        "accuracy": round(correct / scored, 4) if scored else 0.0,
        "ocr_error_rate": round(ocr_errors / scored, 4) if scored else 0.0,
        "tier_breakdown": {
            "local": {"correct": correct, "wrong": wrong},
            "unresolved": missed,
        },
        "latency_ms": {
            "preprocess": _mean(preprocess_ms),
            "ocr": _mean(ocr_ms),
            "match": _mean(match_ms),
            "total": _mean(total_ms),
        },
        "failures": failures,
    }


def main() -> None:
    args = parse_args()
    report = run(args.images, args.labels, args.threshold, args.dataset)
    for key, value in report.items():
        print(f"{key:>24}: {value}")
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"report written to {args.output}")


if __name__ == "__main__":
    main()
