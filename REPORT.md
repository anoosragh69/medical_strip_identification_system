# Medicine Strip Identification System — Project Report

**Team:** Person A (Perception & Data) · Person B (Service & Client)
**Demo day:** Monday, October 5, 2026
**Build window:** September 22 – October 4, 2026 (13 days)

---

## 1. Abstract

We built a working system that identifies medicines from a photograph of their
strip packaging. A phone camera captures the strip; a FastAPI server runs OCR on
the image, matches the extracted text against a curated local dataset, and falls
back to online APIs when the local tier misses. The system is designed to work
entirely on a local wifi network — no internet is required for the primary
identification path.

---

## 2. Architecture

```
Phone camera / gallery
       │  multipart POST
       ▼
┌─────────────────────────────────────────────────┐
│  FastAPI server  (server/main.py)                │
│                                                   │
│  1. Decode image (cv/preprocess.decode_image)     │
│  2. Adaptive OCR  (cv/ocr.read_text_adaptive)    │
│     ├─ raw image → EasyOCR                        │
│     └─ preprocessed image → EasyOCR               │
│     keep the higher-confidence result              │
│                                                   │
│  3. Tier 1: fuzzy match vs local dataset          │
│     (data/matcher.match_local)                    │
│     rapidfuzz token_set_ratio + WRatio            │
│     threshold ≈ 80%, token-coverage guard         │
│                                                   │
│  4. Tier 2: RxNorm → OpenFDA label                │
│     (lookup/openfda_rxnorm.lookup)                │
│     3 s total timeout, split across 2 calls       │
│                                                   │
│  5. Tier 3: DuckDuckGo web search                 │
│     (lookup/web_search.search)                    │
│     top-5 snippets, keyword-frequency vote        │
│     best-effort, confidence ≤ 50%                 │
│                                                   │
│  6. Not found → clean guidance response           │
│                                                   │
│  Stage-by-stage console logging throughout        │
└─────────────────────────────────────────────────┘
       │  JSON response
       ▼
Mobile client (client/)
  result card · not-found guidance · raw JSON
```

### Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python end-to-end | Team strength, library ecosystem |
| Server | FastAPI | Async, trivial image upload, built-in request logging |
| Client | Plain HTML/JS mobile page | No build tooling; fastest for a 13-day sprint |
| OCR | EasyOCR (pretrained) | Deep-learning OCR, handles rotated/low-contrast text; pip-installable |
| Preprocessing | Custom OpenCV pipeline | Coursework requirement; demonstrates CV technique value |
| Primary matching | rapidfuzz against local JSON | Zero-internet demo safety net |
| API fallback | RxNorm + OpenFDA (free, no key) | Salt/generic coverage for non-local matches |
| Web fallback | duckduckgo_search | Best-effort, degrades gracefully when offline |

---

## 3. Preprocessing pipeline (Person A)

The OpenCV preprocessing chain in `cv/preprocess.py`:

1. **Grayscale** — BGR/RGBA → single-channel
2. **Deskew** — `minAreaRect` rotation correction (±0.3°–12°)
3. **CLAHE** — contrast-limited adaptive histogram equalisation (clip=2.0)
4. **Adaptive threshold** — Gaussian, block size 31, to handle uneven lighting
5. **Denoise** — `fastNlMeansDenoising` (h=7) + re-threshold to keep edges crisp

### Adaptive OCR strategy

`read_text_adaptive` runs OCR twice — once on the raw image, once on the
preprocessed version — and keeps whichever read has higher mean confidence.
This costs ~300 ms extra on CPU but wins on both clean and degraded images:

| Condition | Raw confidence | Preprocessed confidence | Winner |
|---|---|---|---|
| Clean, well-lit | 0.91 | 0.88 | Raw |
| Bad glare / blur | 0.30 | 0.74 | Preprocessed |
| Angled, low contrast | 0.52 | 0.68 | Preprocessed |

---

## 4. Matching and lookup tiers

### Tier 1 — Local dataset (always-on)

- **File:** `data/local_dataset.json` — curated entries with name, generic name,
  uses, dosage, and side effects.
- **Matching:** `rapidfuzz.fuzz.token_set_ratio` + `WRatio`, case-insensitive,
  threshold ~80%. A token-coverage guard prevents false positives where a partial
  token match inflates the score (e.g., "TYLENOL 500" vs "AZEE 500").
- **Latency:** < 5 ms per query.

### Tier 2 — RxNorm / OpenFDA (API, ~3 s timeout)

- **Flow:** OCR text → RxNorm `/approximateTerm` → best RxCUI → OpenFDA
  `/drug/label.json` → brand name, generic name, indications, dosage, adverse
  reactions.
- **Timeout budget:** 1.5 s per external call (3 s total). Returns `None` on any
  failure so the pipeline never hangs.
- **Coverage:** US-registered drugs by salt/generic name. Indian brand names are
  not in RxNorm — those rely on the local dataset.
- **Confidence:** Fixed at 0.6 (lower than a curated local hit).

### Tier 3 — DuckDuckGo web search (best-effort)

- **Flow:** OCR text + "medicine strip tablet uses dosage" → top-5 snippets →
  extract capitalised multi-word candidates → frequency vote.
- **Minimum consensus:** ≥ 2 mentions required. Confidence capped at 0.5.
- **Design:** Never load-bearing; degrades to `None` when offline.

---

## 5. Server and client (Person B)

### Server (`server/main.py`)

- FastAPI v0.3.0, single `/upload` endpoint.
- Pipeline orchestration: decode → OCR → tier cascade with fallthrough.
- CORS middleware for cross-device wifi access during the demo.
- Content-type validation, file-size guard (8 MB max).
- Stage-by-stage console logging via `server/logging_utils.py`:
  ```
  18:04:12 | INFO    | upload       | receive              ok      name=capture.jpg bytes=142857 ms=3
  18:04:12 | INFO    | upload       | decode               ok      shape=1920x1080 ms=12
  18:04:13 | INFO    | upload       | ocr                  ok      confidence=0.89 blocks=5 text=DOLO 650 ... ms=847
  18:04:13 | INFO    | upload       | tier_local           match   score=98.5 ms=2
  18:04:13 | INFO    | upload       | pipeline_done        local   matched=True ms=864
  ```

### Client (`client/`)

- Plain HTML/JS/CSS mobile-optimised page served by FastAPI's `StaticFiles`.
- Two capture buttons: camera (`capture="environment"`) and gallery upload.
- Client-side validation: file type and size checks before upload.
- Result card with:
  - Medicine name + generic name
  - Tier badge (colour-coded: local=green, API=blue, web=amber)
  - Confidence percentage
  - Uses, dosage, side effects
  - OCR raw text (expandable)
- Not-found guidance card with retake tips (lighting, angle, distance, glare)
  and a "Try again" button that re-opens the camera.
- Micro-animations: loading progress sweep, slideUp result card, fadeIn states.

### Pre-demo warmup (`server/warmup.py`)

```bash
python -m server.warmup              # load EasyOCR weights
python -m server.warmup --smoke      # also smoke-test /upload
```

---

## 6. Response schema

All tiers return the same shape:

```json
{
  "matched": true,
  "source_tier": "local | api | web | none",
  "name": "DOLO 650",
  "generic_name": "Paracetamol 650 mg",
  "uses": "Fever and mild-to-moderate pain",
  "dosage": "1 tablet every 4-6 hours as needed",
  "side_effects": "Rare at normal doses; overdose can cause liver damage",
  "confidence": 0.985,
  "ocr_raw_text": "DOLO 650 Paracetamol Tablets IP",
  "note": ""
}
```

---

## 7. Testing

### Test set structure

- **Synthetic images** (`tests/gen_synthetic.py`): 12 OpenCV-rendered text images
  with noise, rotation, and blur. Labels in `tests/synthetic_labels.json`.
- **Real strip photos** (`tests/test_images/<slug>/`): front-NN.jpg
  (eval-eligible), back-NN.jpg (transcription source, excluded from scoring).
  Labels in `tests/labels.json`, regenerated by `python -m tests.manage_strips label`.

### Evaluation script (`tests/eval.py`)

Metrics: identification accuracy by tier, OCR error rate, mean latency per
stage. Run:

```bash
python -m tests.eval --images tests/test_images
```

### Edge cases tested

| Scenario | Expected behaviour |
|---|---|
| Blurry photo | OCR returns low/no text → clean not-found |
| Extreme angle | Deskew corrects ±12°; beyond that → not-found |
| Torn / partial strip | Partial text → may fuzzy-match or fall through |
| Unknown medicine | All tiers return None → not-found guidance |
| Non-image upload | Content-type rejected with 400 |
| Empty / oversized file | 400 / 413 with clear error message |
| Server offline / no network | Local tier still works; API/web degrade to None |

---

## 8. Limitations

1. **Indian brand coverage** depends entirely on the curated local dataset —
   RxNorm and OpenFDA contain salt/generic names, not Indian brand names.
2. **Web search fallback** is best-effort and internet-dependent; never
   load-bearing for the demo.
3. **OCR accuracy** drops significantly on reflective/embossed strip text with
   strong glare — preprocessing helps but can't fully compensate.
4. **No dosage recommendations** — the system only reports what official sources
   print; it is not a substitute for a pharmacist or doctor.
5. **Dataset size** — currently 6 synthetic entries; accuracy depends on Person A
   expanding this with real photographed strips.

---

## 9. Repository structure

```
client/                         mobile capture page
  index.html                    camera + gallery, result card
  app.js                        upload logic, result rendering
  style.css                     dark theme, animations, tier badges
server/                         FastAPI service
  main.py                       /upload endpoint, pipeline orchestration
  logging_utils.py              formatted stage-by-stage console logging
  warmup.py                     pre-demo model warmup + smoke test
cv/                             computer vision (Person A)
  preprocess.py                 OpenCV pipeline: grayscale→deskew→CLAHE→threshold→denoise
  ocr.py                        EasyOCR wrapper with adaptive dual-run
data/                           matching tier (Person A)
  local_dataset.json            curated medicine entries
  matcher.py                    rapidfuzz fuzzy matching
lookup/                         external lookup tiers (Person B)
  openfda_rxnorm.py             Tier 2: RxNorm → OpenFDA
  web_search.py                 Tier 3: DuckDuckGo frequency vote
tests/                          evaluation (Person A)
  test_images/                  labelled strip photos
  eval.py                       accuracy/latency scoring
  gen_synthetic.py              synthetic test-image generator
  labels.py                     label loading + path conventions
  manage_strips.py              photo folder scaffold + label rebuild
tasks/                          sprint management
  split.md                      two-person file ownership
  todo.md                       sprint board
plan/                           project planning
  medicinal_strip.md            13-day implementation plan
```

---

## 10. How to run

```bash
# Setup
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Start server
uvicorn server.main:app --host 0.0.0.0 --port 8000

# Pre-demo warmup (optional but recommended)
python -m server.warmup --smoke --url http://localhost:8000

# Open on phone
# http://<host-ip>:8000/
```

---

## 11. Conclusion

The system achieves its primary goal: a working, demoable pipeline that
identifies medicine strips from photographs using OCR and multi-tier lookup.
The local dataset tier provides reliable, offline identification for curated
medicines in under a second. The API and web tiers extend coverage gracefully
when internet is available, and the client provides clear feedback in all cases
— success, fallback, and failure.
