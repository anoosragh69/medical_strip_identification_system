"""EasyOCR wrapper: image in, raw text + confidence out.

Owner: Person A (see tasks/split.md). The reader is a process-wide singleton so
model weights load once — pre-warm it before the demo (see plan, Oct 5).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

__all__ = ["OcrResult", "read_text", "get_reader"]


@dataclass
class OcrResult:
    text: str
    confidence: float  # mean word confidence, 0.0-1.0
    elapsed_ms: float


_reader = None


def get_reader():
    """Lazily construct the EasyOCR reader (downloads weights on first use)."""
    global _reader
    if _reader is None:
        import easyocr

        _reader = easyocr.Reader(["en"], gpu=True)
    return _reader


def read_text(image: np.ndarray) -> OcrResult:
    """Run OCR over a (preprocessed) image and aggregate the text blocks."""
    raise NotImplementedError("Person A: implement in Day 2")
