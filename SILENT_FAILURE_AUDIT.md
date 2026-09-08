# SILENT_FAILURE_AUDIT.md — Task 2.6

**Scope discipline observed:** this task inspects `ai_engine/` and `backend/` for the
silent-failure pattern found in the CRNN path. It fixes nothing outside `anpr_engine.py`,
and nothing is fixed here either — Task 2.6 is report-only, same as 2.5.

All forward-pass tests below ran against **OpenCV 5.0.0.93** (built as a standalone venv
from the `cp37-abi3` wheel, matching `venv/pyvenv.cfg`'s declared Python 3.10.11 target and
the production `cv2.dnn` version), not the OpenCV 4.13.0 I mistakenly used in Task 2. That
distinction is the entire reason this audit was necessary — see `ANPR_PHANTOM_TRACE.md` for
the correction.

---

## 1. Model execution audit

| Component | Model | Expects at first layer | Code feeds | Executes? | Evidence |
|---|---|---|---|---|---|
| `anpr_engine.py` CRNN | `text_recognition_CRNN_EN_2021sep.onnx` | `Conv_0`: `[N,1,32,100]` (1-channel) | `recognize_plate()` passes 3-channel BGR (`cv2.cvtColor(..., COLOR_GRAY2BGR)` on every one of its 4 passes) | **Yes, under OpenCV 5.0.0.93.** Fails under OpenCV 4.13.0 with `(-215) ngroups > 0 && inpCn % ngroups == 0`. | Isolated repro in both versions; see `ANPR_PHANTOM_TRACE.md`. Real forward pass returns a string; stored DB rows reconcile against `clean_and_validate_plate_text()` output (29/30 distinct values match exactly). |
| `face_engine.py` YuNet | `face_detection_yunet_2023mar.onnx` | `FaceDetectorYN_create` input, dynamic `(w,h)` via `setInputSize` | `detect_primary_face()` calls `setInputSize((w,h))` then `detect(img_bgr)` with the actual crop dimensions | **Yes.** | Isolated forward pass on a synthetic 640x480 BGR frame: ran without exception, returned `faces=None` (expected — random noise contains no face). No exception, no silent swallow. |
| `face_engine.py` SFace | `face_recognition_sface_2021dec.onnx` | `alignCrop` input: any BGR image + a 15-value `face_info` row (bbox + 5 landmarks + score); `feature` input: the aligned 112x112x3 crop | `extract_embedding()` calls `recognizer.alignCrop(img_bgr, face_info)` then `recognizer.feature(aligned_face)` | **Yes.** | Isolated forward pass with a synthetic `face_info` row: `alignCrop` → `(112,112,3)` uint8, `feature` → `(1,128)` float32, non-zero norm (5.222). Correct shape at every stage. |
| `detector.py` YOLOv8n | `yolov8n.pt` | Ultralytics `YOLO.predict()`, internal preprocessing | `self.model.predict(frame, conf=self.conf_threshold, ...)` | **Not directly re-verified — `ultralytics` is not installed in either interpreter used in this audit.** Indirect evidence only. | `detections` table: 4,906 `VEHICLE` + 3,640 `PERSON` + 2 `ANIMAL` rows, confidence range 20.0–98.97 (mean 74.9), a continuous distribution — not the handful of fixed constants the broken ANPR scorer produces. Consistent with genuine model output, but not a substitute for a direct forward-pass check. |

**Follow-up needed, not performed here (out of scope for a report-only task):** install
`ultralytics` in the reconstructed venv (Task 4 does this anyway) and run one real
`YOLO.predict()` call to close this gap with direct evidence rather than distributional
inference.

### Why YuNet/SFace did not fail like CRNN did

The CRNN bug is a **channel-count mismatch that OpenCV 4.x's DNN validates and OpenCV 5.x's
new graph engine does not** (`net_impl_backend.cpp` in OpenCV 5 logs `"Targets are not
supported by the new graph engine for now"` as a warning, not an error, on every model
load — worth watching for other silent behavior changes across the 4→5 boundary).

`face_engine.py` never constructs a fixed-shape array by hand — `alignCrop` and `detect`
take the raw image and a dynamically-set input size, so there is no equivalent hardcoded
channel assumption to get wrong. This is a structural reason the same bug class is unlikely
here, not just an absence of an observed symptom.

---

## 2. Silent exception handlers

`grep -rn` across `ai_engine/` and `backend/` for bare/broad handlers that could mask a
`forward()`-level failure:

| file:line | Handler | Encloses inference? | Verdict |
|---|---|---|---|
| `ai_engine/intelligence/anpr_engine.py:322-323` | `except Exception: pass` | **Yes** — wraps `self.model.recognize(p_img)` inside the 4-pass loop | **The exact pattern that caused the Task 2 misdiagnosis.** Currently not firing in production (OpenCV 5 accepts the input), but it means a future dependency change that reintroduces the shape mismatch would fail exactly as silently as it appeared to in my OpenCV-4.13 test. This is the highest-value fix candidate for Task 6, independent of the OCR model swap. |
| `ai_engine/intelligence/threat_engine.py:411-412` | `except Exception as e: logger.debug(...)` | No — wraps an HTTP POST to the backend (`_post_detection` or similar), not a model call | Acceptable. Logs at DEBUG, but the guarded operation is a network call, not inference; a failure here drops a detection event, not silently, since it's logged (if DEBUG is enabled). |
| `backend/database/init_db.py:47-48` | `except Exception: pass` | No — wraps `ALTER TABLE ADD COLUMN`, used to no-op when the column already exists | Acceptable, arguably still fragile: it swallows *any* exception (e.g. a locked DB, a disk error), not just "column already exists". Not a model-inference issue, out of scope here. |
| `backend/websocket/manager.py:58-59` | `except Exception as e: logger.debug(...)` | No — WebSocket broadcast fallback | Acceptable, same reasoning as threat_engine.py. |

**Only one handler in the entire audited surface wraps a model `forward()` call, and it is
the one already implicated.** No second dead model was found via this method.

---

## 3. Readiness-flag audit

| Flag | Location | Set on | What it actually proves |
|---|---|---|---|
| `ANPREngine.is_ready` | `anpr_engine.py:75` | `self.model is not None`, set in `_load_model()` after `cv2.dnn.readNet()` + `dnn_TextRecognitionModel()` construction succeed | **Construction only.** Proves the ONNX file parsed and the network graph built. Says nothing about whether a `recognize()` call on real input will succeed — which is exactly why the Task 2 misdiagnosis was possible: `is_ready` reported `True` in both OpenCV versions, one of which never returns usable output. |
| `FaceEngine.is_ready` | `face_engine.py:82-83` | `self.detector is not None and self.recognizer is not None`, set after both `cv2.FaceDetectorYN_create()` and `cv2.FaceRecognizerSF_create()` succeed | Same category: construction only. In this audit it happens to be trustworthy today (both models were forward-tested and work), but the flag itself carries no forward-pass guarantee, and nothing in the code enforces one. |
| `Detector` (YOLO) — no `is_ready` property exists; `self.model` is checked implicitly | `detector.py:73-87` | `self.model` assigned after `YOLO(path)` construction inside a try/except that logs on failure but does not re-raise | Same category, and the weakest of the three: there is not even a named readiness property — callers presumably check `self.model is not None` directly or assume it loaded. Not verified further here (ultralytics not installed in this audit's interpreters); flagged as a gap above. |

**General finding:** every readiness flag in the audited surface is a **construction-success**
flag, not an **inference-success** flag. This is the same design defect in three places, and
it is precisely the defect that let the CRNN bug go unnoticed for however long the system
has been "working." Task 6 should not repeat this pattern for the new `fast-plate-ocr` /
`fast-alpr` stack: `is_ready` (or its replacement) should reflect at least one successful
forward pass, not just successful construction, ideally verified at load time with a
canned input.

---

## Summary table

| Component | Model | Expects | Receives | Executes | In scope for this rebuild? |
|---|---|---|---|---|---|
| ANPR OCR | CRNN_EN | 1-channel | 3-channel | Yes (OpenCV 5 only — version-fragile) | **Yes** — this file is being replaced in Task 6 regardless |
| ANPR OCR silent handler | — | — | — | Masks failures | **Yes** — same file, same task |
| ANPR readiness flag | — | — | — | Construction-only | **Yes** — worth fixing in the same rewrite |
| Face detection | YuNet | dynamic | dynamic, matched | Yes, verified | **No** — out of scope, no defect found |
| Face recognition | SFace | 112x112x3 aligned crop | matched via `alignCrop` | Yes, verified | **No** — out of scope, no defect found |
| Face readiness flag | — | — | — | Construction-only (same pattern) | **No** — report to operator as separate finding, not fixed here per scope discipline |
| Vehicle/person detection | YOLOv8n | Ultralytics-internal | Ultralytics-internal | **Not directly verified** (`ultralytics` not installed in either audit interpreter); indirect evidence (varied real-looking confidence distribution) is consistent with working | **No** — out of scope; recommend a direct forward-pass check once `ultralytics` is installed in Task 4's venv, since that installs it anyway |

### Items to report to the operator, not fixed here

1. **`FaceEngine.is_ready` and the (absent) YOLO readiness check are construction-only,
   same as the ANPR flag was.** No defect currently observed in either, but the pattern is
   identical to the one that hid the CRNN issue. Recommend a follow-up task, separate from
   this rebuild, to make readiness checks verify one real forward pass at load time across
   all three engines.
2. **YOLOv8n has not been directly forward-tested in this audit** (missing dependency in
   both interpreters used). Distributional evidence from the DB is reassuring but not
   proof. Recommend closing this gap as soon as the Task 4 venv has `ultralytics` installed
   — a two-line check, not a new task.
3. **`backend/database/init_db.py:47-48`'s bare `except Exception: pass`** swallows more
   than the "column already exists" case it's meant to. Low severity, unrelated to model
   inference, flagged for completeness since it matched the grep pattern.

No component outside `anpr_engine.py` requires a code change as a result of this audit.
