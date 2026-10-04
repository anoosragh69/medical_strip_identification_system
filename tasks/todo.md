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
- [x] `A` Photograph 20-30 physical strips, 5-6 photos each (angles/lighting/distance) into `tests/test_images/` — **deferred to Day 4, completed there Oct 4 (8 strips, 1 angle each)**
- [x] `A` Fill `data/local_dataset.json` from each strip's package info (name, generic, uses, dosage, side effects) — **deferred with the photography, completed on Day 4**
- [x] `A` `cv/preprocess.py`: grayscale → deskew → CLAHE → adaptive threshold → denoise — **pulled forward from Day 2; deskew verified to ±9° rotation**
- [x] `A` Synthetic test images in `tests/test_images/` (OpenCV-rendered text + noise) so schema and OCR wiring can be checked before real strip photos exist — 12 images + `tests/synthetic_labels.json`, before/after previews in `tests/artifacts/`
- [x] `A` `cv/ocr.py`: EasyOCR wrapper returning concatenated text + average confidence — **pulled forward from Day 2; full 12-image synthetic sweep run, adaptive dual-run added after raw-vs-pre comparison**

### Day 2 — Wed Sept 23
- [x] `A` Visual before/after check on 8-10 sample images — 12 synthetic previews in `tests/artifacts/`; real-strip pass happens with the Day 4 retune
- [x] `A` `data/matcher.py`: rapidfuzz match against the local dataset, threshold ~80 — **12/12 synthetic images match correctly, all negative controls fall through; case-insensitive token matching added after a token-order miss**
- [x] `A` Temporary fake `local_dataset.json` seeded with the 6 synthetic medicines — **real strip data replaces it on Day 4**
- [x] `B` (if free) Plan the tier-2/3 lookup interfaces so Day 4 unblocks cleanly — **interfaces defined in stubs; implemented on Day 11**

### Day 3 — Thu Sept 24
- [x] `A` Run OCR on the available test set (synthetic until photos land) with and without preprocessing; log the accuracy delta — **12-image results: raw 12/12 @ 281ms, preprocessed-only 11/12 @ 272ms, adaptive 12/12 @ 543ms. Preprocessing's value showed on the degraded cases (confidence 0.30 → 0.74 on synth_09) rather than raw label hits, because synthetic text is easier than a real strip photo — re-measure on real strips after Day 4**
- [x] `A+B` Wire preprocess → OCR → local match into `/upload`, returning results from the temporary dataset entries — **verified over HTTP: stage logs with ms timings, <1s per request, error paths return 400, unknown medicine falls through to a clean not-found**
- [x] `A` Fix the WRatio false positive found during smoke testing (unknown "TYLENOL 500" scored 85.5 against "AZEE 500") — **token-coverage guard added; 12/12 + all negatives clean**
- [x] `A` Fit the real strip photography session in here if it slips from Day 1 — **slipped to Day 4 as planned**

### Day 4 — Fri Sept 25
- [x] `A` Photograph the strips and fill the real `local_dataset.json` — **done Oct 4: 8 strips (acenext-p, brufen-400, dolo-650, gelusil-mps, levipil-500, levocetirizine-5, loperamide-2, metrogyl-400), front+back each, converted from JXL to `tests/test_images/<slug>/front-01.jpg` + `back-01.jpg`, `manage_strips label` → 8 fronts labelled, backs excluded. Dataset replaced with the 8 real entries (+ GELUSIL alias). Demo scope: 8 strips, clean-angle photo only — no 02/03/04 angle variants yet**
- [x] `A` Retune preprocessing params (CLAHE clip, threshold block size, deskew) against the real photos — **done Oct 4, outcome is the opposite of the synthetic set: binarisation destroys real glossy-foil text (5 of 8 strips lost their brand name after preprocessing; a param sweep over 7 variants never beat raw). Fix: `read_text_adaptive` now only prefers the preprocessed read when it beats raw by ≥0.25 confidence, so raw wins on real photos while synth_09's rescue (0.30→0.74) still holds. Two matcher fixes rode along: `partial_ratio` added to `score_pair` (glued-prefix reads like "RLevocetirizine" scored 57 despite full coverage) and curated `aliases` support (OCR never reads "MPS" in Gelusil-MPS). Result: real 8/8, synthetic 12/12, negatives clean**
- [x] `B` `lookup/openfda_rxnorm.py`: RxNorm → OpenFDA label, ~3s timeout, never blocks the demo — **implemented Day 11: RxNorm approximate-term → RxCUI → OpenFDA label, timeout split 1.5s per API call, returns None on any failure**
- [x] `B` `lookup/web_search.py`: `duckduckgo_search` top-5 snippets + frequency vote — **implemented Day 11: keyword-frequency vote over top-5 snippets, ≥2 mentions required, confidence capped at 0.5**
- [x] `B` Chain all three tiers with fallthrough logic and the shared response schema — **server's _resolve_tiers() already handled fallthrough; now lookup modules return real results instead of NotImplementedError**

### Day 5 — Sat Sept 26
- [x] `B` Formatted console logging at every stage (received → preprocessed → OCR → tier → match → sent) — **already in place since Day 3 wiring; logging_utils.py with stage_timer context manager**
- [x] `B` Client result card: name, uses, dosage, side effects, resolving tier — **polished Day 11: tier-colored badges (local=green, api=blue, web=amber), OCR text display, slideUp animation**
- [x] `B` Clean "not found anywhere" path on server and client — **polished Day 11: dedicated not-found guidance card with retake tips and retry button**
- [ ] `A+B` Full end-to-end run on the same wifi, no other network assumptions
- [ ] `A+B` **Checkpoint: core pipeline works end-to-end tonight**

### Day 6 — Sun Sept 27 (buffer)
- [ ] `A+B` Catch up on anything slipped from Days 1-5
- [x] `A` Expand the local dataset if time allows — **done Oct 4: 8 real strip entries replace the synthetic 6 (synthetic names preserved in `tests/synthetic_dataset.json` for the regression harness)**

## Week 2 — harden, test, stretch

### Day 7 — Mon Sept 28
- [x] `A` `tests/eval.py` over the labeled set: accuracy by tier, OCR error rate, latency per stage — **implemented Oct 4 (Day 11): real set 8/8 accuracy, OCR error 0.125 (gelusil's "MPS" never OCRs, alias covers it), local tier 100%, ~3.1s/photo (OCR 2.9s dominates; synthetic was 0.61s). Synthetic regression: 12/12 @ 0.61s. Reports in `tests/artifacts/eval_report_real.json` + `eval_report.json`**
- [x] `A+B` Fix what the numbers expose; local-dataset path must be near 100% — **fixed Oct 4: baseline was 5/8 with 3 OCR/matcher failures; all three root causes fixed (adaptive selection margin, partial_ratio scoring, GELUSIL alias) → 8/8, and HTTP smokes on gelusil/brufen/metrogyl + bad-payload 400 all pass against the hardened server**

### Day 8 — Tue Sept 29
- [x] `B` Edge cases: blurry, extreme angle, torn strip, unknown medicine → graceful failure — **Day 11: client-side validation (file type/size), not-found card with retake guidance, server returns clean JSON on all error paths**
- [x] `A` Tune the fuzzy-match threshold from Day 7 error patterns — **no error patterns left after the Day 7 fixes: threshold stays 80, negative controls (TYLENOL/ADVIL/unknown/empty) clean on both datasets. Revisit if angle/glare variants expose misses**

### Day 9 — Wed Sept 30
- [ ] `A` Stretch goal only if core is solid: text-region detector to crop the brand name (RTX 3050 / Colab)
- [ ] `B` Otherwise keep hardening the core path; a working core beats an unfinished stretch goal

### Day 10 — Thu Oct 1
- [ ] `A` Continue stretch goal, or `B` polish UI / response formatting / log readability
- [x] `B` Start the report: architecture + dataset methodology — **completed in REPORT.md**

### Day 11 — Fri Oct 2
- [ ] `A` Keep the detector only if it measurably beats the plain preprocessed-crop path
- [ ] `A` Re-run `tests/eval.py`, confirm nothing regressed
- [x] `B` Implement openfda_rxnorm.py and web_search.py (replaced NotImplementedError stubs)
- [x] `B` Polish client: not-found card, tier badges, OCR display, retry flow, animations
- [x] `B` Response formatting: tier-specific confidence, truncated API fields to 500 chars
- [x] `B` Report draft started — **completed in REPORT.md**

### Day 12 — Sat Oct 3
- [x] `B` Finalize report: results, numbers, limitations, before/after screenshots — **REPORT.md created**
- [x] `A+B` Full demo rehearsal script (`server/rehearsal.py`) and verification routine created

### Day 13 — Sun Oct 4
- [ ] `A+B` Final buffer — fix rehearsal findings only, no new features
- [ ] `A` Prepare 2-3 known-good strips plus one "not found" example

### Mon Oct 5 — demo day
- [x] `B` Warm up the EasyOCR model before the demo starts — **`server/warmup.py` created and lifespan pre-warming implemented**
- [ ] `A+B` Known-good strips first, then the graceful-failure example

---

## Standing rules

- No commit messages like "step 3 done" — describe *what changed and why*.
- Whoever touches a shared file (especially `server/main.py`) writes the integration note in the next commit body.
- Anything that blocks the local-only demo path gets fixed before any stretch work.
