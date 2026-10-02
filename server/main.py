"""FastAPI service: photo in, medicine information out.

Run from the repository root:

    uvicorn server.main:app --host 0.0.0.0 --port 8000

then open http://<host-ip>:8000/ on a phone on the same network.

The pipeline itself is owned across tasks/split.md: A owns cv/ and data/,
B owns this file and lookup/. Until the stages land, /upload answers with the
response schema marked source_tier="none" so the client contract is testable.
"""

from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from cv.ocr import OcrResult, read_text_adaptive, warm_up
from cv.preprocess import decode_image
from data.matcher import match_local
from lookup import openfda_rxnorm, web_search
from server.logging_utils import log_stage, new_logger

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = REPO_ROOT / "client"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load EasyOCR weights at server start so the first upload isn't the slow one."""
    warm_up()
    yield


app = FastAPI(title="Medicine Strip Identification System", version="0.2.0", lifespan=lifespan)
log = new_logger("upload")


def build_response(
    *,
    matched: bool,
    source_tier: str,
    name: str = "",
    generic_name: str = "",
    uses: str = "",
    dosage: str = "",
    side_effects: str = "",
    confidence: float = 0.0,
    ocr_raw_text: str = "",
    note: str = "",
) -> dict:
    """The one place response shapes are built — every tier uses this."""
    return {
        "matched": matched,
        "source_tier": source_tier,
        "name": name,
        "generic_name": generic_name,
        "uses": uses,
        "dosage": dosage,
        "side_effects": side_effects,
        "confidence": confidence,
        "ocr_raw_text": ocr_raw_text,
        "note": note,
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    """Accept one strip photo and return the identification result.

    Pipeline: decode -> adaptive OCR -> local match -> openfda/rxnorm -> web search.
    Each tier returns the shared schema or falls through; exceptions in any tier
    degrade to the next one rather than failing the request.
    """
    started = time.perf_counter()
    payload = await file.read()
    log_stage(
        log,
        "receive",
        "ok",
        (time.perf_counter() - started) * 1000,
        name=file.filename,
        bytes=len(payload),
        content_type=file.content_type,
    )

    if not payload:
        return JSONResponse(status_code=400, content=build_response(matched=False, source_tier="none", note="empty file"))
    if len(payload) > MAX_UPLOAD_BYTES:
        return JSONResponse(status_code=413, content=build_response(matched=False, source_tier="none", note="file too large"))

    started = time.perf_counter()
    try:
        image = decode_image(payload)
    except ValueError as error:
        log_stage(log, "decode", "error", (time.perf_counter() - started) * 1000, reason=str(error))
        return JSONResponse(status_code=400, content=build_response(matched=False, source_tier="none", note="not a readable image"))
    log_stage(log, "decode", "ok", (time.perf_counter() - started) * 1000, shape="x".join(map(str, image.shape[:2])))

    started = time.perf_counter()
    ocr = read_text_adaptive(image)  # preprocesses internally
    wall_ms = (time.perf_counter() - started) * 1000
    log_stage(log, "ocr", "ok" if ocr.text else "empty", wall_ms, confidence=f"{ocr.confidence:.2f}", blocks=ocr.blocks, text=ocr.text[:60])
    if not ocr.text:
        return JSONResponse(content=build_response(matched=False, source_tier="none", note="no text found in the photo"))

    result = _resolve_tiers(ocr)
    return JSONResponse(content=result)


def _resolve_tiers(ocr: OcrResult) -> dict:
    """Try local -> api -> web, returning the first tier that resolves."""
    started = time.perf_counter()
    match = match_local(ocr.text)
    log_stage(log, "tier_local", "match" if match else "no_match", (time.perf_counter() - started) * 1000, score=match.score if match else 0)
    if match:
        record = match.record or {}
        return build_response(
            matched=True,
            source_tier="local",
            name=match.name,
            generic_name=record.get("generic_name", ""),
            uses=record.get("uses", ""),
            dosage=record.get("dosage", ""),
            side_effects=record.get("side_effects", ""),
            confidence=round(match.score / 100, 3),
            ocr_raw_text=ocr.text,
        )

    for tier, lookup_fn in (("api", openfda_rxnorm.lookup), ("web", web_search.search)):
        started = time.perf_counter()
        try:
            result = lookup_fn(ocr.text)
        except NotImplementedError:
            log_stage(log, f"tier_{tier}", "pending")
            continue
        except Exception as error:  # noqa: BLE001 - a dead network must not kill the demo path
            log_stage(log, f"tier_{tier}", "error", (time.perf_counter() - started) * 1000, reason=str(error)[:80])
            continue
        log_stage(log, f"tier_{tier}", "match" if result else "no_match", (time.perf_counter() - started) * 1000)
        if result:
            result["ocr_raw_text"] = ocr.text
            return result

    return build_response(matched=False, source_tier="none", ocr_raw_text=ocr.text, note="couldn't identify - retake the photo")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(CLIENT_DIR / "index.html")


# Registered last: explicit routes above always win over the static mount.
from fastapi.staticfiles import StaticFiles  # noqa: E402

app.mount("/", StaticFiles(directory=CLIENT_DIR, html=True), name="client")
