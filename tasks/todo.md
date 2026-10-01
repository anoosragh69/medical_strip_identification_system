# Sprint To-Do — Medicine Strip Identification System

**Demo day:** Mon Oct 5, 2026 · 13 build days from Tue Sept 22
**Source of truth for scope:** [`plan/medicinal_strip.md`](../plan/medicinal_strip.md)
**Who does what:** see [`split.md`](split.md)

Legend: `[ ]` not started · `[~]` in progress · `[x]` done · `A`/`B` owner · `A+B` both

---

## Sprint 0 — repository bootstrap

- [x] `A+B` Create `tasks/` folder with this board and the two-person split
- [x] `A+B` Scaffold repo layout (`client/ server/ cv/ data/ lookup/ tests/`) with importable module stubs
- [x] `B` FastAPI `/upload` endpoint accepting an image and returning the dummy response schema
- [x] `B` Mobile client page with camera + gallery buttons that POST to `/upload` and render the JSON
- [x] `B` Stage-by-stage console logging helper (`server/logging_utils.py`)
- [x] `A+B` `README.md`, `requirements.txt`, `.gitignore`

## Week 1 — core pipeline

### Day 1 — Tue Sept 22
- [x] `A+B` Repo + folder structure created
- [x] `B` FastAPI skeleton returns dummy JSON
- [x] `B` Client camera/gallery capture + raw JSON display
- [ ] `A` Photograph 20-30 physical strips, 5-6 photos each (angles/lighting/distance) into `tests/test_images/` — **deferred to Day 4 alongside matcher work; no sessions available today**
- [ ] `A` Fill `data/local_dataset.json` from each strip's package info (name, generic, uses, dosage, side effects) — **deferred with the photography; temporary fake entries unblock matcher development**
- [x] `A` `cv/preprocess.py`: grayscale → deskew → CLAHE → adaptive threshold → denoise — **pulled forward from Day 2; deskew verified to ±9° rotation**
- [x] `A` Synthetic test images in `tests/test_images/` (OpenCV-rendered text + noise) so schema and OCR wiring can be checked before real strip photos exist — 12 images + `tests/labels.json`, before/after previews in `tests/artifacts/`
- [x] `A` `cv/ocr.py`: EasyOCR wrapper returning concatenated text + average confidence — **pulled forward from Day 2; full 12-image synthetic sweep run, adaptive dual-run added after raw-vs-pre comparison**

### Day 2 — Wed Sept 23
- [x] `A` Visual before/after check on 8-10 sample images — 12 synthetic previews in `tests/artifacts/`; real-strip pass happens with the Day 4 retune
- [x] `A` `data/matcher.py`: rapidfuzz match against the local dataset, threshold ~80 — **12/12 synthetic images match correctly, all negative controls fall through; case-insensitive token matching added after a token-order miss**
- [x] `A` Temporary fake `local_dataset.json` seeded with the 6 synthetic medicines — **real strip data replaces it on Day 4**
- [ ] `B` (if free) Plan the tier-2/3 lookup interfaces so Day 4 unblocks cleanly

### Day 3 — Thu Sept 24
- [ ] `A` Run OCR on the available test set (synthetic until photos land) with and without preprocessing; log the accuracy delta
- [ ] `A+B` Wire preprocess → OCR → local match into `/upload`, returning results from the temporary dataset entries
- [ ] `A` Fit the real strip photography session in here if it slips from Day 1

### Day 4 — Fri Sept 25
- [ ] `A` Photograph the strips and fill the real `local_dataset.json` — **latest hard deadline; replaces the temporary entries**
- [ ] `A` Retune preprocessing params (CLAHE clip, threshold block size, deskew) against the real photos — plastic glare ≠ synthetic noise
- [ ] `B` `lookup/openfda_rxnorm.py`: RxNorm → OpenFDA label, ~3s timeout, never blocks the demo
- [ ] `B` `lookup/web_search.py`: `duckduckgo_search` top-5 snippets + frequency vote
- [ ] `B` Chain all three tiers with fallthrough logic and the shared response schema

### Day 5 — Sat Sept 26
- [ ] `B` Formatted console logging at every stage (received → preprocessed → OCR → tier → match → sent)
- [ ] `B` Client result card: name, uses, dosage, side effects, resolving tier
- [ ] `B` Clean "not found anywhere" path on server and client
- [ ] `A+B` Full end-to-end run on the same wifi, no other network assumptions
- [ ] `A+B` **Checkpoint: core pipeline works end-to-end tonight**

### Day 6 — Sun Sept 27 (buffer)
- [ ] `A+B` Catch up on anything slipped from Days 1-5
- [ ] `A` Expand the local dataset if time allows

## Week 2 — harden, test, stretch

### Day 7 — Mon Sept 28
- [ ] `A` `tests/eval.py` over the labeled set: accuracy by tier, OCR error rate, latency per stage
- [ ] `A+B` Fix what the numbers expose; local-dataset path must be near 100%

### Day 8 — Tue Sept 29
- [ ] `B` Edge cases: blurry, extreme angle, torn strip, unknown medicine → graceful failure
- [ ] `A` Tune the fuzzy-match threshold from Day 7 error patterns

### Day 9 — Wed Sept 30
- [ ] `A` Stretch goal only if core is solid: text-region detector to crop the brand name (RTX 3050 / Colab)
- [ ] `B` Otherwise keep hardening the core path; a working core beats an unfinished stretch goal

### Day 10 — Thu Oct 1
- [ ] `A` Continue stretch goal, or `B` polish UI / response formatting / log readability
- [ ] `B` Start the report: architecture + dataset methodology

### Day 11 — Fri Oct 2
- [ ] `A` Keep the detector only if it measurably beats the plain preprocessed-crop path
- [ ] `A` Re-run `tests/eval.py`, confirm nothing regressed

### Day 12 — Sat Oct 3
- [ ] `B` Finalize report: results, numbers, limitations, before/after screenshots
- [ ] `A+B` Full demo rehearsal, ideally on the demo wifi

### Day 13 — Sun Oct 4
- [ ] `A+B` Final buffer — fix rehearsal findings only, no new features
- [ ] `A` Prepare 2-3 known-good strips plus one "not found" example

### Mon Oct 5 — demo day
- [ ] `B` Warm up the EasyOCR model before the demo starts
- [ ] `A+B` Known-good strips first, then the graceful-failure example

---

## Standing rules

- No commit messages like "step 3 done" — describe *what changed and why*.
- Whoever touches a shared file (especially `server/main.py`) writes the integration note in the next commit body.
- Anything that blocks the local-only demo path gets fixed before any stretch work.
