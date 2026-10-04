"""Pre-demo warm-up script.

Owner: Person B (see tasks/split.md). Run this before the live demo to:
1. Load EasyOCR model weights (first inference downloads ~100 MB)
2. Verify the server responds on /healthz
3. Run a quick smoke test with a synthetic image if available

Usage:
    python -m server.warmup              # just warm up the model
    python -m server.warmup --smoke      # warm up + hit /upload with a test image
    python -m server.warmup --url http://192.168.1.5:8000  # specify server URL
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_IMAGES = REPO_ROOT / "tests" / "test_images"


def warm_ocr() -> None:
    """Force-load the EasyOCR model weights so the first demo photo isn't slow."""
    print("[warmup] Loading EasyOCR model weights...")
    started = time.perf_counter()
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from cv.ocr import warm_up
        warm_up()
        elapsed = time.perf_counter() - started
        print(f"[warmup] EasyOCR ready in {elapsed:.1f}s")
    except (ImportError, ModuleNotFoundError) as err:
        print(f"[warmup] [WARN] Could not import EasyOCR ({err}). Install dependencies from requirements.txt before running the live server.")


def check_health(base_url: str) -> bool:
    """Ping /healthz and return True if the server is up."""
    import urllib.request
    import json
    try:
        req = urllib.request.Request(f"{base_url}/healthz")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "ok":
                    print(f"[warmup] Server healthy at {base_url}")
                    return True
    except Exception as exc:
        print(f"[warmup] Server not reachable at {base_url}: {exc}")
    return False


def smoke_test(base_url: str) -> None:
    """POST a test image to /upload and print the result summary."""
    import urllib.request
    import json

    # Find any test image to use
    candidates = list(TEST_IMAGES.rglob("*.png")) + list(TEST_IMAGES.rglob("*.jpg"))
    if not candidates:
        print("[warmup] No test images found in tests/test_images/ — skipping smoke test")
        return

    test_image = candidates[0]
    print(f"[warmup] Smoke test with: {test_image.relative_to(REPO_ROOT)}")

    started = time.perf_counter()
    with open(test_image, "rb") as f:
        img_bytes = f.read()

    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{test_image.name}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + img_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            elapsed_ms = (time.perf_counter() - started) * 1000
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("matched"):
                print(f"[warmup] ✓ Identified: {data['name']} via {data['source_tier']} "
                      f"({data['confidence']*100:.0f}% confidence) in {elapsed_ms:.0f}ms")
            else:
                print(f"[warmup] ✗ Not matched (note: {data.get('note', '?')}) in {elapsed_ms:.0f}ms")
    except Exception as exc:
        print(f"[warmup] ✗ Server upload failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-demo warm-up and smoke test.")
    parser.add_argument("--smoke", action="store_true", help="Also run a smoke test against /upload")
    parser.add_argument("--url", default="http://localhost:8000", help="Server base URL (default: http://localhost:8000)")
    args = parser.parse_args()

    warm_ocr()

    if args.smoke:
        if check_health(args.url):
            smoke_test(args.url)
        else:
            print("[warmup] Start the server first: uvicorn server.main:app --host 0.0.0.0 --port 8000")
            sys.exit(1)

    print("[warmup] Done. Ready for demo.")


if __name__ == "__main__":
    main()
