"""EasyOCR wrapper: image in, raw text + confidence out.

Owner: Person A (see tasks/split.md). The reader is a process-wide singleton so
model weights load once - pre-warm it before the demo (see plan, Oct 5). GPU is
used when torch sees CUDA, otherwise it falls back to CPU automatically.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

__all__ = ["OcrResult", "read_text", "read_text_adaptive", "get_reader", "warm_up"]

LANGUAGES = ["en"]


@dataclass
class OcrResult:
    text: str
    confidence: float  # mean block confidence, 0.0-1.0
    elapsed_ms: float
    blocks: int


_reader = None


def get_reader():
    """Lazily construct the EasyOCR reader (downloads model weights on first use)."""
    global _reader
    if _reader is None:
        import easyocr
        import torch

        _reader = easyocr.Reader(LANGUAGES, gpu=torch.cuda.is_available(), verbose=False)
    return _reader


def warm_up() -> None:
    """Force model-weight load now, not mid-demo."""
    get_reader()


def _sort_key(block) -> tuple[int, int]:
    """Order text blocks top-to-bottom, left-to-right from their bounding box."""
    points = block[0]
    top = min(int(point[1]) for point in points)
    left = min(int(point[0]) for point in points)
    return top, left


def read_text(image: np.ndarray) -> OcrResult:
    """Run OCR over a (preprocessed) image and aggregate the text blocks."""
    reader = get_reader()
    started = time.perf_counter()
    blocks = reader.readtext(image)
    elapsed_ms = (time.perf_counter() - started) * 1000

    if not blocks:
        return OcrResult(text="", confidence=0.0, elapsed_ms=elapsed_ms, blocks=0)

    blocks = sorted(blocks, key=_sort_key)
    words = [str(text) for _, text, _ in blocks]
    confidence = float(np.mean([float(conf) for _, _, conf in blocks]))
    return OcrResult(
        text=" ".join(words),
        confidence=confidence,
        elapsed_ms=elapsed_ms,
        blocks=len(blocks),
    )


def read_text_adaptive(image: np.ndarray) -> OcrResult:
    """Run OCR on both the raw and preprocessed variants, keep the higher-confidence read.

    Measured on the synthetic set (tests/synthetic_labels.json): preprocessing rescues
    degraded shots (raw 0.30 -> pre 0.74 on the bad-glare blur case) but on
    clean shots binarisation can *lower* confidence. Dual-running costs one
    extra ~300ms on CPU and wins on both ends of the distribution, so this is
    the function server/main.py should call once wired.
    """
    from cv.preprocess import preprocess  # lazy: avoids a hard import cycle

    raw_result = read_text(image)
    preprocessed = preprocess(image)
    pre_result = read_text(preprocessed)

    best = pre_result if pre_result.confidence > raw_result.confidence else raw_result
    return OcrResult(
        text=best.text,
        confidence=best.confidence,
        elapsed_ms=raw_result.elapsed_ms + pre_result.elapsed_ms,
        blocks=best.blocks,
    )
