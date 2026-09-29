# Medicine Strip Identification System — Implementation Plan

**Deadline:** Monday, Oct 5, 2026 (demo day) — 13 build days from today, Tue Sept 22
**Goal:** A working, live-demoable pipeline. Local wifi only during demo (no guaranteed internet).
**Team:** working as one unit, no fixed role split — tasks below are ordered so they can be picked up in parallel where marked.

---

## 1. Final decisions locked in

| Decision | Choice | Why |
|---|---|---|
| Language | Python end-to-end | your team's strength |
| Server | FastAPI | async, trivial image upload endpoint, built-in request logging |
| Client | Plain HTML/JS mobile webpage | fastest to build, no build tooling needed for a 6-day sprint |
| Image input | Camera capture **and** gallery upload | two buttons: `<input capture="environment">` for camera, plain `<input type="file" accept="image/*">` for gallery |
| OCR library | **EasyOCR** | deep-learning based, handles small/rotated/low-contrast text far better than Tesseract out of the box; pip-installable; can run on your RTX 3050 or CPU fallback if GPU isn't free during the demo |
| Preprocessing | Custom OpenCV pipeline, written by you (not EasyOCR's internal handling) | this is where your CV coursework grade lives |
| Data tier 1 | Local curated dataset (JSON/SQLite) | must work with zero internet — your demo safety net |
| Data tier 2 | OpenFDA + RxNorm (free, no key needed at your volume) | salt/generic name coverage only — Indian brand names won't be in these |
| Data tier 3 | Web search fallback via `duckduckgo_search` (free, no API key) | best-effort only, treat as optional/degradable |
| GPU | RTX 3050 locally + Colab as backup | enough for EasyOCR inference and any light experimentation; **not** enough time to train a custom OCR recognizer from scratch — see Section 6 |
| Team split | None — sequential/parallel task list below, pick up whatever's next | |

**Important framing for your report:** because classroom wifi is unreliable, the local dataset tier must be treated as the primary, always-on path. The API and web-search tiers are enhancements that degrade gracefully (short timeout → fall through) rather than something the demo depends on.

---

## 2. System architecture

```
[Phone: camera or gallery] 
        |  photo (multipart POST)
        v
[FastAPI server] --- logs every stage to console, formatted ---
        |
        v
[Preprocessing (OpenCV)]
   grayscale -> deskew -> CLAHE contrast -> adaptive threshold -> denoise
        |
        v
[OCR (EasyOCR)] -> raw text + confidence score
        |
        v
[Fuzzy match vs local dataset] -----match found (score > 80%)----> [Format response]
        | no match / low confidence
        v
[OpenFDA / RxNorm lookup by extracted text] --match found--> [Format response]
        | no match / API timeout
        v
[Web search fallback: top 5 results, frequency vote] --match found--> [Format response]
        | nothing found anywhere
        v
[Return "couldn't identify, retake photo" response]
```

Response schema (same shape regardless of which tier resolved it):
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

---

## 3. Repo structure

```
/client
  index.html        # capture UI (camera + gallery buttons, result display)
  app.js
  style.css
/server
  main.py            # FastAPI app, upload endpoint, orchestrates the pipeline
  logging_utils.py    # formatted stage-by-stage console logging
/cv
  preprocess.py       # OpenCV pipeline
  ocr.py              # EasyOCR wrapper
/data
  local_dataset.json  # your curated 15-30 medicine entries
  matcher.py           # rapidfuzz matching against local_dataset.json
/lookup
  openfda_rxnorm.py    # tier 2
  web_search.py         # tier 3
/tests
  test_images/           # labeled photos for accuracy testing
  eval.py                 # accuracy/latency scoring script
plan.md
README.md
```

---

## 4. Day-by-day schedule

### Week 1 — build the core pipeline

**Day 1 — Tue Sept 22 (today)**
- [ ] Repo + folder structure created
- [ ] FastAPI skeleton: `/upload` endpoint accepting an image, returns dummy JSON
- [ ] Client page: camera capture button + gallery upload button, both POST to `/upload`, display raw JSON response
- [ ] Start photographing your physical strips: aim for 20-30 medicines, 5-6 photos each (different angles/lighting/distance) — this doubles as your test set and your local dataset source images
- [ ] Manually fill `local_dataset.json` for each medicine (name, generic name, uses, dosage, side effects) from the strip's own package info

**Day 2 — Wed Sept 23**
- [ ] `preprocess.py`: grayscale → deskew (`cv2.minAreaRect` on largest text contour, or Hough line-based) → CLAHE contrast → adaptive threshold → light denoise (`fastNlMeansDenoising`)
- [ ] Test preprocessing visually on 8-10 sample photos, save before/after images for your report
- [ ] `ocr.py`: wrap EasyOCR (`reader.readtext(image)`), return concatenated text + average confidence

**Day 3 — Thu Sept 24**
- [ ] Run OCR on your full test set, **with and without** preprocessing — log accuracy difference (this is your key evidence of CV technique value)
- [ ] `matcher.py`: fuzzy match OCR output against `local_dataset.json` names using `rapidfuzz`, threshold ~80%
- [ ] Wire preprocessing → OCR → local match into the FastAPI endpoint, return real results for strips in your dataset

**Day 4 — Fri Sept 25**
- [ ] `openfda_rxnorm.py`: query RxNorm for approximate name match → get RxCUI → query OpenFDA label endpoint for uses/dosage/warnings; set a short timeout (~3s) so it never blocks the demo
- [ ] `web_search.py`: `duckduckgo_search` query with extracted text, take top 5 snippets, simple keyword-frequency vote on candidate drug names against a known drug-name wordlist
- [ ] Chain all three tiers in the endpoint with fallthrough logic and consistent response schema

**Day 5 — Sat Sept 26**
- [ ] Formatted console logging at every stage (image received → preprocessing done → OCR text+confidence → tier attempted → match/no match → response sent)
- [ ] Client: polish result display (show medicine name, uses, dosage, side effects, and which tier answered)
- [ ] Handle "not found anywhere" path cleanly on both server and client
- [ ] Full end-to-end test on same wifi network, no other network assumptions
- [ ] **Checkpoint: core pipeline should be fully working end-to-end by tonight** — everything from Week 2 onward is refinement, testing, and stretch goals

**Day 6 — Sun Sept 27**
- [ ] Buffer day — catch up on anything slipped from Days 1-5
- [ ] Expand local dataset further if time allows (more medicines = more reliable demo)

### Week 2 — harden, test, and go beyond the basics

**Day 7 — Mon Sept 28**
- [ ] Run `eval.py` across your full labeled test set: accuracy % broken down by tier, OCR error rate, average latency per stage
- [ ] Fix whatever the numbers expose — prioritize the local-dataset path working close to 100% of the time, since that's your demo safety net

**Day 8 — Tue Sept 29**
- [ ] Edge-case testing: blurry photo, extreme angle, partial/torn strip, unknown medicine — confirm each fails gracefully instead of crashing
- [ ] Tune the fuzzy-match confidence threshold based on real error patterns from Day 7's eval

**Day 9 — Wed Sept 30 (stretch goal window opens)**
- [ ] If the core path is solid: attempt the stretch goal from Section 6 (custom text-region detector to crop the brand-name area before OCR) using your RTX 3050 / Colab
- [ ] If not solid yet: keep hardening the core path instead — a working core beats an unfinished stretch goal

**Day 10 — Thu Oct 1**
- [ ] Continue stretch goal or polish (UI, response formatting, logging readability)
- [ ] Start drafting the report: architecture, dataset methodology so far

**Day 11 — Fri Oct 2**
- [ ] Finish stretch goal work, integrate it back into the main pipeline if it improved accuracy — otherwise leave it out, don't risk demo stability for a marginal gain
- [ ] Re-run `eval.py` to confirm nothing regressed

**Day 12 — Sat Oct 3**
- [ ] Finalize report: results, numbers, limitations, screenshots of before/after preprocessing
- [ ] Full rehearsal of the live demo, ideally on the actual demo wifi

**Day 13 — Sun Oct 4**
- [ ] Final buffer day — fix anything the rehearsal exposed, no new features
- [ ] Prepare 2-3 known-good strips plus one "not found" example for the demo

**Mon Oct 5 — Demo day**
- [ ] Pre-load/warm up EasyOCR model before the demo starts (first inference is slow to load weights)
- [ ] Have your known-good strips ready first, then the "not found" example to show graceful failure

---

## 5. Testing plan

- **OCR accuracy**: word/character error rate on your labeled test set, before vs. after preprocessing.
- **End-to-end accuracy**: % of test strips correctly identified, broken down by which tier resolved them.
- **Edge cases to explicitly test**: blurry photo, extreme angle, partial/torn strip, a medicine not in your dataset or any API (should hit "not found" cleanly, not crash).
- **Latency**: log time per stage so you can report a breakdown (preprocessing / OCR / lookup).

---

## 6. What's realistic vs. not, given 13 days

**Realistic and worth doing:** the full OpenCV preprocessing pipeline, using EasyOCR pretrained (no training needed), fuzzy matching, tiered fallback logic, formatted logging, a clean demo UI, thorough testing with real numbers — all comfortably fits in Week 1 plus the hardening days of Week 2.

**Now a genuine stretch goal (Days 9-11), not just "not realistic":** a small custom text-region detector, trained on your own photographed strips, to localize and crop just the brand-name area before handing it to OCR. With your RTX 3050 / Colab and ~20-30 labeled medicines from Day 1, a lightweight detector (e.g. a small YOLO variant or a simple bounding-box regressor) is achievable in 2-3 days — but only attempt it once the core pipeline (Week 1 checkpoint) is fully working, and only keep it in the final build if it measurably improves accuracy over the plain preprocessed-crop approach.

**Still not realistic, don't attempt:** training a full custom OCR recognizer (character-level text recognition) from scratch — that needs far more labeled data and training time than a 13-day project supports, even with GPU access. Stick with EasyOCR's pretrained recognizer throughout.

---

## 7. Known limitations to state up front in your report

- OpenFDA/RxNorm only cover salt/generic names, not Indian brand names — brand coverage relies on your local dataset and the web-search fallback.
- Web-search fallback is best-effort and depends on internet availability, which is not guaranteed during the demo.
- This is an identification/info tool, not a substitute for a pharmacist or doctor — no dosage recommendations are made, only what's printed on official sources.
