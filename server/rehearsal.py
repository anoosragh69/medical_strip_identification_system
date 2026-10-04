"""Demo rehearsal checklist and automated verification.

Owner: Person B (see tasks/split.md). Run this before the live demo to verify
that every piece of the pipeline works end-to-end.

Usage:
    python -m server.rehearsal                            # default localhost
    python -m server.rehearsal --url http://192.168.1.5:8000  # custom URL
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_IMAGES = REPO_ROOT / "tests" / "test_images"

PASS = "OK"
FAIL = "FAIL"
WARN = "WARN"


def check(label: str, passed: bool, detail: str = "") -> bool:
    mark = PASS if passed else FAIL
    msg = f"  [{mark}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return passed


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, str, bytes]:
    import urllib.request
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return resp.status, resp.headers.get_content_charset() or "utf-8", data
    except urllib.error.HTTPError as err:
        data = err.read()
        return err.code, err.headers.get_content_charset() or "utf-8", data


def _http_post_file(url: str, filename: str, content: bytes, content_type: str = "image/png", timeout: float = 30.0) -> tuple[int, str, bytes]:
    import urllib.request
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return resp.status, resp.headers.get_content_charset() or "utf-8", data
    except urllib.error.HTTPError as err:
        data = err.read()
        return err.code, err.headers.get_content_charset() or "utf-8", data


def run_rehearsal(base_url: str) -> None:
    import json

    results = []
    print("\n" + "=" * 60)
    print("  DEMO REHEARSAL — Medicine Strip Identification System")
    print("=" * 60)
    print(f"\n  Server: {base_url}")
    print(f"  Time:   {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. Server health
    print("1. Server health")
    try:
        status, _, body = _http_get(f"{base_url}/healthz", timeout=5)
        data = json.loads(body.decode("utf-8"))
        results.append(check("GET /healthz returns 200", status == 200, f"status={status}"))
        results.append(check("/healthz body is ok", data.get("status") == "ok"))
    except Exception as exc:
        results.append(check("Server reachable", False, str(exc)))
        print("\n  Server not reachable. Start it first:")
        print("    uvicorn server.main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # 2. Client page loads
    print("\n2. Client page")
    try:
        status_root, _, body_root = _http_get(f"{base_url}/", timeout=5)
        html_text = body_root.decode("utf-8")
        results.append(check("GET / returns HTML", status_root == 200 and "Medicine Strip" in html_text))

        status_css, _, _ = _http_get(f"{base_url}/style.css", timeout=5)
        results.append(check("CSS loads", status_css == 200))

        status_js, _, _ = _http_get(f"{base_url}/app.js", timeout=5)
        results.append(check("JS loads", status_js == 200))
    except Exception as exc:
        results.append(check("Client accessible", False, str(exc)))

    # 3. Upload with a test image (known-good)
    print("\n3. Known-good image upload")
    test_images = list(TEST_IMAGES.rglob("*.png")) + list(TEST_IMAGES.rglob("*.jpg"))
    if test_images:
        img = test_images[0]
        try:
            started = time.perf_counter()
            with open(img, "rb") as f:
                img_bytes = f.read()
            status, _, body = _http_post_file(f"{base_url}/upload", img.name, img_bytes, "image/png", timeout=30)
            elapsed_ms = (time.perf_counter() - started) * 1000
            data = json.loads(body.decode("utf-8"))
            results.append(check("POST /upload returns 200", status == 200))
            results.append(check("Response has 'matched' field", "matched" in data))
            results.append(check("Response has 'source_tier' field", "source_tier" in data))
            results.append(check("Response has 'ocr_raw_text' field", "ocr_raw_text" in data))
            results.append(check(f"Latency < 5 s", elapsed_ms < 5000, f"{elapsed_ms:.0f}ms"))
            if data.get("matched"):
                results.append(check(f"Identified as: {data.get('name')}", True, f"tier={data.get('source_tier')} conf={data.get('confidence', 0):.2f}"))
            else:
                print(f"  [{WARN}] Image not matched — this may be expected for: {img.name}")
        except Exception as exc:
            results.append(check("Upload succeeded", False, str(exc)))
    else:
        print(f"  [{WARN}] No test images found in {TEST_IMAGES.relative_to(REPO_ROOT)}")

    # 4. Error handling
    print("\n4. Error handling")
    try:
        # Empty upload
        status_empty, _, _ = _http_post_file(f"{base_url}/upload", "empty.jpg", b"", "image/jpeg", timeout=10)
        results.append(check("Empty file returns 400", status_empty == 400))

        # Non-image file
        status_txt, _, _ = _http_post_file(f"{base_url}/upload", "test.txt", b"not an image", "text/plain", timeout=10)
        results.append(check("Non-image content-type returns 400", status_txt == 400))

        # Corrupt image bytes
        status_corrupt, _, _ = _http_post_file(f"{base_url}/upload", "corrupt.jpg", b"\xff\xd8\xff\x00garbage", "image/jpeg", timeout=10)
        results.append(check("Corrupt image returns 400", status_corrupt == 400))
    except Exception as exc:
        results.append(check("Error handling", False, str(exc)))

    # 5. API tier availability (informational)
    print("\n5. External tier availability (informational)")
    try:
        status_rx, _, _ = _http_get("https://rxnav.nlm.nih.gov/REST/version.json", timeout=5)
        results.append(check("RxNorm API reachable", status_rx == 200))
    except Exception:
        print(f"  [{WARN}] RxNorm not reachable — tier 2 will degrade gracefully")

    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            r = list(ddgs.text("paracetamol medicine", max_results=1))
        results.append(check("DuckDuckGo reachable", len(r) > 0))
    except Exception:
        print(f"  [{WARN}] DuckDuckGo not reachable — tier 3 will degrade gracefully")

    # Summary
    passed = sum(1 for r in results if r)
    total = len(results)
    print()
    print("=" * 60)
    print(f"  RESULT: {passed}/{total} checks passed")
    if passed == total:
        print("  All systems go. Ready for demo! 🎉")
    else:
        print(f"  {total - passed} issue(s) to fix before demo.")
    print("=" * 60)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo rehearsal: verify every pipeline stage.")
    parser.add_argument("--url", default="http://localhost:8000", help="Server base URL")
    args = parser.parse_args()
    run_rehearsal(args.url)


if __name__ == "__main__":
    main()
