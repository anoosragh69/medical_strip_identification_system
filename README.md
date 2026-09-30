# Medicine Strip Identification System

Photograph a medicine strip with a phone; the server reads the text with OCR,
matches it against a curated local dataset, and falls back to external lookups
when the local tier misses. Designed to run on a local network with **no
internet required for the primary path**.

**Demo day:** Mon Oct 5, 2026 · **Plan:** [`plan/medicinal_strip.md`](plan/medicinal_strip.md) · **Work split:** [`tasks/split.md`](tasks/split.md) · **Board:** [`tasks/todo.md`](tasks/todo.md)

## How it works

```
phone photo -> POST /upload -> preprocess (OpenCV) -> OCR (EasyOCR)
            -> fuzzy match vs local dataset          (tier 1, always on)
            -> RxNorm / OpenFDA                      (tier 2, ~3s timeout)
            -> DuckDuckGo frequency vote             (tier 3, best effort)
            -> shared JSON response
```

## Layout

```
client/    mobile capture page: camera + gallery buttons, result card
server/    FastAPI app (/upload), stage-by-stage console logging
cv/        OpenCV preprocessing pipeline, EasyOCR wrapper
data/      local_dataset.json (curated strips), rapidfuzz matcher
lookup/    openfda_rxnorm.py (tier 2), web_search.py (tier 3)
tests/     test_images/ labelled photos, eval.py accuracy/latency scoring
tasks/     sprint board and the two-person split
plan/      original 13-day implementation plan
```

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Open `http://<host-ip>:8000/` on a phone on the same network. First run
downloads the EasyOCR model weights, so warm the model before a demo.

## Status

Skeleton is in place: `/upload` accepts an image and returns the response
schema, and the client renders it. The pipeline stages are stubs raising
`NotImplementedError` and are being filled in per [`tasks/todo.md`](tasks/todo.md).

## Response schema

```json
{
  "matched": true,
  "source_tier": "local | api | web | none",
  "name": "string",
  "generic_name": "string",
  "uses": "string",
  "dosage": "string",
  "side_effects": "string",
  "confidence": 0.0,
  "ocr_raw_text": "string"
}
```

## Disclaimer

Identification and reference information only — not a substitute for a
pharmacist or doctor, and no dosage recommendations beyond what the official
sources print.
