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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from server.logging_utils import log_stage, new_logger

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = REPO_ROOT / "client"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

app = FastAPI(title="Medicine Strip Identification System", version="0.1.0")
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

    Pipeline once wired (Day 3 onward):
        preprocess -> ocr -> match_local -> openfda_rxnorm -> web_search
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

    # Day 3 onward: preprocess -> ocr -> match_local -> openfda_rxnorm -> web_search,
    # each stage emitting its own log_stage line with timing.
    return JSONResponse(
        content=build_response(
            matched=False,
            source_tier="none",
            ocr_raw_text="",
            note="skeleton: pipeline not wired yet (Day 3)",
        )
    )


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(CLIENT_DIR / "index.html")


# Registered last: explicit routes above always win over the static mount.
from fastapi.staticfiles import StaticFiles  # noqa: E402

app.mount("/", StaticFiles(directory=CLIENT_DIR, html=True), name="client")
