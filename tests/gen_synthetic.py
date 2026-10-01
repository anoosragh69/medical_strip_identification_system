"""Generate synthetic medicine-strip images for early pipeline testing.

Renders simple labelled 'strip' photos (text on a lit metallic-ish backdrop)
with realistic corruptions - rotation, blur, noise, glare, uneven lighting -
so preprocess.py and ocr.py can be exercised before the real photographs land
on Day 4. Also writes tests/labels.json mapping each image to its expected
medicine name, the same file tests/eval.py will consume later.

Usage:
    python -m tests.gen_synthetic            # regenerate the default set
    python -m tests.gen_synthetic --count 20 --hardness hard
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

TEST_IMAGES = Path(__file__).resolve().parent / "test_images"
LABELS = Path(__file__).resolve().parent / "labels.json"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"

# Name + generic line pairs. These are the same medicines the temporary
# fake local_dataset.json uses, so matcher.py can be tested against the
# same vocabulary the images render.
STRIPS = [
    ("DOLO 650", "Paracetamol Tablets IP 650mg"),
    ("AZEE 500", "Azithromycin Tablets IP 500mg"),
    ("CROCIN ADVANCE", "Paracetamol 500mg"),
    ("NEERAL 25", "Metoprolol Succinate 25mg"),
    ("PANTODAC 40", "Pantoprazole 40mg"),
    ("VELMOL", "Aceclofenac 100mg + Serratiopeptidase"),
]

FONT = cv2.FONT_HERSHEY_SIMPLEX
SEED = 22


def base_backdrop(width: int, height: int, rng: np.random.Generator) -> np.ndarray:
    """Metallic-foil style backdrop: soft lighting gradient + mild noise."""
    base_value = rng.integers(150, 205)
    backdrop = np.full((height, width), base_value, dtype=np.float32)

    # Sinusoidal shading across the width mimics foil curvature.
    columns = np.linspace(0, rng.uniform(1.5, 3.5) * np.pi, width)
    shading = (np.sin(columns) * rng.uniform(15, 40)).astype(np.float32)
    backdrop += shading[np.newaxis, :]

    noise = rng.normal(0, rng.uniform(3, 9), (height, width)).astype(np.float32)
    backdrop += noise
    return np.clip(backdrop, 0, 255).astype(np.uint8)


def draw_text(backdrop: np.ndarray, name: str, generic: str, rng: np.random.Generator) -> np.ndarray:
    """Draw the brand name line and a smaller generic-info line."""
    height, width = backdrop.shape
    ink = rng.integers(15, 60)

    name_scale = rng.uniform(1.1, 1.5)
    name_thickness = int(rng.integers(2, 4))
    name_size, _ = cv2.getTextSize(name, FONT, name_scale, name_thickness)
    name_x = int(rng.integers(10, max(11, width - name_size[0] - 10)))
    name_y = height // 2
    cv2.putText(backdrop, name, (name_x, name_y), FONT, name_scale, int(ink), name_thickness)

    generic_scale = 0.4
    cv2.putText(
        backdrop,
        generic,
        (name_x, min(height - 8, name_y + 22)),
        FONT,
        generic_scale,
        int(ink) + 20,
        1,
    )
    return backdrop


def rotate(image: np.ndarray, angle_deg: float) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle_deg, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)


def add_glare(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Bright ellipse of reflected light somewhere over the text area."""
    out = image.astype(np.float32)
    height, width = image.shape[:2]
    center = (int(rng.uniform(0.2, 0.8) * width), int(rng.uniform(0.2, 0.8) * height))
    axes = (int(rng.uniform(30, 90)), int(rng.uniform(15, 40)))
    mask = np.zeros_like(image, dtype=np.uint8)
    cv2.ellipse(mask, center, axes, float(rng.uniform(0, 180)), 0, 360, 255, -1)
    mask = cv2.GaussianBlur(mask, (41, 41), 0)
    strength = rng.uniform(60, 110)
    out += (mask.astype(np.float32) / 255.0) * strength
    return np.clip(out, 0, 255).astype(np.uint8)


def generate(count: int, out_dir: Path, hardness: str) -> dict[str, str]:
    rng = np.random.default_rng(SEED)
    labels: dict[str, str] = {}

    for index in range(count):
        name, generic = STRIPS[index % len(STRIPS)]
        width, height = int(rng.integers(360, 520)), int(rng.integers(120, 200))

        image = base_backdrop(width, height, rng)
        image = draw_text(image, name, generic, rng)

        max_angle = 5.0 if hardness == "easy" else 9.0
        image = rotate(image, float(rng.uniform(-max_angle, max_angle)))

        if hardness != "easy":
            if rng.random() < 0.5:
                image = add_glare(image, rng)
            if rng.random() < 0.5:
                kernel = int(rng.integers(3, 8)) * 2 + 1
                image = cv2.GaussianBlur(image, (kernel, kernel), 0)

        filename = f"synth_{index + 1:02d}.jpg"
        cv2.imwrite(str(out_dir / filename), image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        labels[filename] = name

    return labels


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic strip images for pipeline testing.")
    parser.add_argument("--count", type=int, default=12, help="images to generate")
    parser.add_argument("--out", type=Path, default=TEST_IMAGES, help="output directory")
    parser.add_argument("--hardness", choices=["easy", "hard"], default="hard", help="corruption level")
    parser.add_argument("--previews", type=bool, default=True, help="also write before/after previews to tests/artifacts")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    labels = generate(args.count, args.out, args.hardness)
    LABELS.write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")
    print(f"generated {len(labels)} images -> {args.out}")
    print(f"labels -> {LABELS}")

    if args.previews:
        from cv.preprocess import preprocess  # noqa: PLC0415 - lazy, kept out of the generator path

        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        for filename in labels:
            raw = cv2.imread(str(args.out / filename))
            combined = np.hstack([raw, cv2.cvtColor(preprocess(raw), cv2.COLOR_GRAY2BGR)])
            cv2.imwrite(str(ARTIFACTS / f"before_after_{filename}"), combined)
        print(f"before/after previews -> {ARTIFACTS}")


if __name__ == "__main__":
    main()
