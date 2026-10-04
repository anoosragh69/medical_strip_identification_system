# Work Split — Two People

The plan's default was "no fixed role split". This file overrides that with a
**file-ownership split** so two people can work in parallel on one checkout
without stepping on each other. Scope, deadlines and architecture are unchanged
from [`plan/medicinal_strip.md`](../plan/medicinal_strip.md).

**Person A — Perception & Data** (what the camera sees and what it means)
**Person B — Service & Client** (how the system is served, driven and explained)

Trunk-based: everyone commits to `master` in small, described commits. No
long-lived branches — the sprint is too short for merge overhead.

---

## 1. File ownership

| Path | Owner | Others may |
|---|---|---|
| `cv/**` | A | read only |
| `data/local_dataset.json` | A | read only |
| `data/matcher.py` | A | B calls it, does not edit |
| `tests/**` | A | add fixtures with A's ack |
| `server/main.py` | B | A edits pipeline call sites (see §3) |
| `server/logging_utils.py` | B | read only |
| `lookup/**` | B | read only |
| `client/**` | B | read only |
| `README.md`, `requirements.txt`, `.gitignore` | B | anyone can append |
| `tasks/**`, `plan/**` | A+B | whoever it concerns updates it |

A shared file edit without an integration note in the commit body is a bug in
the process, not just the code.

---

## 2. What each person owns

### Person A — Perception & Data

1. **Photographing the strips** — 20-30 medicines × 5-6 photos, stored under
   `tests/test_images/`, and hand-filling `data/local_dataset.json` from the
   package inserts.
2. **`cv/preprocess.py`** — grayscale → deskew → CLAHE → adaptive threshold →
   fastNlMeansDenoising, plus saved before/after images for the report.
3. **`cv/ocr.py`** — EasyOCR wrapper: `readtext` → concatenated text + mean
   confidence + elapsed ms.
4. **`data/matcher.py`** — rapidfuzz scoring against the local dataset with a
   tunable cutoff (~80%).
5. **`tests/eval.py`** — accuracy by tier, OCR error rate, latency per stage;
   the numbers that justify the CV work in the report.
6. **Stretch goal (Days 9-11)** — custom text-region detector trained on A's
   own photos, kept only if it beats the plain preprocessed path.

### Person B — Service & Client

1. **`server/main.py`** — `/upload`, request validation, pipeline orchestration,
   tier fallthrough, response schema, static serving of the client.
2. **`server/logging_utils.py`** — one formatted line per stage with timing.
3. **`client/`** — camera and gallery capture, upload, result card (name,
   generic, uses, dosage, side effects, resolving tier, confidence), and the
   clean not-found state.
4. **`lookup/openfda_rxnorm.py`** — RxNorm approximate match → canonical name
   (properties fallback for unnamed candidates) → OpenFDA label by generic
   name; 2 s per call, ~6 s ceiling so the demo never hangs. (Revised
   2026-10-04: the by-RxCUI OpenFDA query 404s for every RxCUI, and the old
   1.5 s per-call budget timed out good calls.)
5. **`lookup/web_search.py`** — `duckduckgo_search` top-5 snippets with a
   keyword-frequency vote; degradable, never load-bearing.
6. **Report + rehearsal (Days 10-13)** — architecture write-up, demo script,
   wifi rehearsal, pre-warming EasyOCR.

---

## 3. Interface contracts

Both sides are written against these signatures before either is finished, so
neither person waits on the other.

```python
# cv/preprocess.py  (A)
def preprocess(image: np.ndarray) -> np.ndarray: ...

# cv/ocr.py  (A)
@dataclass
class OcrResult:
    text: str
    confidence: float      # mean block confidence, 0.0-1.0
    elapsed_ms: float
    blocks: int
def read_text(image: np.ndarray) -> OcrResult: ...
def read_text_adaptive(image: np.ndarray) -> OcrResult: ...  # raw vs preprocessed, higher confidence wins — prefer this at call sites

# data/matcher.py  (A)
@dataclass
class MatchResult:
    matched: bool
    name: str
    score: float            # 0-100 fuzzy score
    record: dict | None     # the matched dataset entry, so the response builder needn't re-read the dataset
def match_local(text: str, score_cutoff: float = 80.0) -> MatchResult | None: ...

# lookup/openfda_rxnorm.py  (B)  — default timeout revised 3.0 → 6.0 on 2026-10-04
def lookup(query: str, timeout: float = 6.0) -> dict | None: ...

# lookup/web_search.py  (B)
def search(query: str, top_k: int = 5) -> dict | None: ...
```

Every lookup tier returns either the shared response schema or `None`, which
means "fall through to the next tier". Nobody formats a response inside their
own module — `server/main.py` does it once.

```json
{
  "matched": true,
  "source_tier": "local | api | web | none",
  "name": "", "generic_name": "", "uses": "",
  "dosage": "", "side_effects": "",
  "confidence": 0.0,
  "ocr_raw_text": ""
}
```

---

## 4. Parallel schedule

| Day | Person A | Person B |
|---|---|---|
| 1 (Tue 22) | Shoot strips, seed `local_dataset.json` | `/upload` skeleton + capture UI (done in bootstrap) |
| 2 (Wed 23) | `preprocess.py`, `ocr.py` | logging helpers, client polish, dataset field review |
| 3 (Thu 24) | Pre/post OCR eval, `matcher.py` | consume A's contracts, wire the local tier into `/upload` |
| 4 (Fri 25) | More dataset entries, eval harness start | OpenFDA/RxNorm tier, web-search tier, fallthrough chain |
| 5 (Sat 26) | Fix whatever integration exposes | stage logging, result card, not-found path |
| 6 (Sun 27) | Buffer + dataset growth | Buffer + client/server polish |
| 7 (Mon 28) | `eval.py` numbers | fix server-side issues the numbers show |
| 8 (Tue 29) | Threshold tuning | edge-case pass (blur, angle, torn, unknown) |
| 9 (Wed 30) | Stretch detector *if core is solid* | hardening / polish |
| 10 (Thu 1) | Detector iteration | report draft + UX polish |
| 11 (Fri 2) | Keep-or-drop detector, re-run eval | report, response formatting |
| 12 (Sat 3) | Demo props + eval confirmation | final report + rehearsal |
| 13 (Sun 4) | Known-good strip set | rehearsal fixes only |
| Oct 5 | Demo: strip set | Demo: warm-up + narration |

Days 6 and 13 are buffers: anything still open from the previous day moves
there rather than getting a new owner.

---

## 5. Hand-off rules

1. **Contract first.** A signature lands in a stub commit before either side is
   implemented; changing it means one commit, announced in the body.
2. **Integration in `server/main.py` is B's** except for the call sites that
   invoke A's `cv/` and `data/` functions — those A edits, and says so in the
   commit body.
3. **A never ships a broken import.** Stubs raise `NotImplementedError`, not
   `SyntaxError`; B's server must stay runnable at every commit.
4. **Nothing external is on the demo path.** The local dataset tier resolves
   first; API and web tiers time out fast and fall through.
5. **Update `tasks/todo.md` in the same commit** as the work it tracks.
6. **Commit messages describe the change**, not the ritual: what was added,
   what it enables, what it breaks.
