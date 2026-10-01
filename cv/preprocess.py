"""OpenCV preprocessing stage of the pipeline.

Pipeline: grayscale -> deskew -> CLAHE -> adaptive threshold -> denoise.

Owner: Person A (see tasks/split.md). Tuned first against synthetic strip
images (tests/gen_synthetic.py); retune CLAHE__CLIP / BLOCK_SIZE / MAX_SKEW_DEG
once the real photographed strips land on Day 4.
"""

from __future__ import annotations

import cv2
import numpy as np

__all__ = [
    "preprocess",
    "grayscale",
    "deskew",
    "enhance_contrast",
    "binarize",
    "denoise",
    "decode_image",
]

# Tuning knobs — kept up top so a session with real photos can adjust in one place.
CLAHE_CLIP = 2.0
CLAHE_TILES = (8, 8)
BLOCK_SIZE = 31        # adaptive threshold neighbourhood (odd)
BLOCK_C = 7            # adaptive threshold constant
MIN_SKEW_DEG = 0.3     # below this the correction costs more than it gains
MAX_SKEW_DEG = 12.0    # above this we're probably rotating junk, not text
DENOISE_STRENGTH = 7   # fastNlMeansDenoising h


def decode_image(data: bytes) -> np.ndarray:
    """Decode an uploaded image payload to a BGR ndarray."""
    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("payload decodes to no recognisable image")
    return image


def grayscale(image: np.ndarray) -> np.ndarray:
    """Convert BGR/RGB/RGBA input to single-channel grayscale."""
    if image.ndim == 2:
        return image
    channels = image.shape[2]
    if channels == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if channels == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    raise ValueError(f"unsupported channel count: {channels}")


def deskew(image: np.ndarray) -> np.ndarray:
    """Correct small rotations using minAreaRect over the dark text pixels.

    Conservative by design: tiny angles are left alone, and angles beyond
    MAX_SKEW_DEG are treated as orientation, not skew, and left alone too.
    """
    dark = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.nonzero(dark))
    if len(coords) < 100:
        return image

    angle = cv2.minAreaRect(coords)[-1]
    # Normalise the rect angle into a signed rotation in (-45, 45].
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < MIN_SKEW_DEG or abs(angle) > MAX_SKEW_DEG:
        return image

    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """CLAHE contrast equalisation for low-contrast or unevenly lit text."""
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILES)
    return clahe.apply(image)


def binarize(image: np.ndarray) -> np.ndarray:
    """Adaptive thresholding so local lighting changes don't kill the text."""
    return cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        BLOCK_SIZE,
        BLOCK_C,
    )


def denoise(image: np.ndarray) -> np.ndarray:
    """Light fastNlMeansDenoising pass to remove speckle left after binarisation."""
    denoised = cv2.fastNlMeansDenoising(image, None, DENOISE_STRENGTH, 7, 21)
    # fastNlMeans on a binary image softens edges; re-threshold to keep it crisp.
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def preprocess(image: np.ndarray) -> np.ndarray:
    """Full preprocessing chain. Returns a single-channel image for OCR."""
    if image.ndim == 3:
        image = grayscale(image)
    image = deskew(image)
    image = enhance_contrast(image)
    image = binarize(image)
    image = denoise(image)
    return image
