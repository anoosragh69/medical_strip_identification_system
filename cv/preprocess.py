"""OpenCV preprocessing stage of the pipeline.

Pipeline: grayscale -> deskew -> CLAHE -> adaptive threshold -> denoise.

Owner: Person A (see tasks/split.md). Every function keeps the stub contract so
server/main.py can call it before the implementation lands.
"""

from __future__ import annotations

import numpy as np

__all__ = ["preprocess", "grayscale", "deskew", "enhance_contrast", "binarize", "denoise"]


def preprocess(image: np.ndarray) -> np.ndarray:
    """Full preprocessing chain. Returns a single-channel image for OCR."""
    raise NotImplementedError("Person A: implement in Day 2")


def grayscale(image: np.ndarray) -> np.ndarray:
    """Convert BGR/RGB input to single-channel grayscale."""
    raise NotImplementedError("Person A: implement in Day 2")


def deskew(image: np.ndarray) -> np.ndarray:
    """Correct rotation using cv2.minAreaRect on the largest text contour."""
    raise NotImplementedError("Person A: implement in Day 2")


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """CLAHE contrast equalisation."""
    raise NotImplementedError("Person A: implement in Day 2")


def binarize(image: np.ndarray) -> np.ndarray:
    """Adaptive thresholding."""
    raise NotImplementedError("Person A: implement in Day 2")


def denoise(image: np.ndarray) -> np.ndarray:
    """Light fastNlMeansDenoising pass."""
    raise NotImplementedError("Person A: implement in Day 2")
