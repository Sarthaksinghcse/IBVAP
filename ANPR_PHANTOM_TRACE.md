# ANPR_PHANTOM_TRACE.md — Task 2.5

**Question asked:** the engine appeared to return `UNREADABLE` for every vehicle, yet plate
strings reach the dashboard and the database. Where do they come from?

**Answer: they are real CRNN output.** There is no mock, no seed, no fabricated string
anywhere in the ANPR path. The premise of this task was wrong, and the error was mine —
see [Correction](#correction-to-the-task-2-finding) below.

---

## Correction to the Task 2 finding

My Task 2 report stated that the CRNN never executes. **That conclusion was
environment-specific and does not hold for the deployed system.**

I tested on system Python 3.12.7 / **OpenCV 4.13.0**, where feeding 3-channel BGR to this
single-channel model raises. Production runs **OpenCV 5.0.0.93**. Re-tested against the
production version, on the same model file, with the exact input `recognize_plate()`
constructs:

| OpenCV | 3-channel BGR (what the engine feeds) | 1-channel gray |
|---|---|---|
| 4.13.0 | **FAIL** — `(-215) ngroups > 0 && inpCn % ngroups == 0` | OK → `'i'` |
| **5.0.0.93 (production)** | **OK → `'i'`** | OK → `'i'` |

OpenCV 5 accepts the channel mismatch that OpenCV 4.13 rejects. The `except Exception:
pass` at `anpr_engine.py:322` is still a real latent hazard — it is what allowed me to
misread the failure — but in production it is not firing on this path.

**Consequence for Amendment 02 §E:** the prescribed baseline framing ("feature
non-functional", "`exact_match = 0.0%` measures a crash") is **factually wrong for the
production venv** and must not be used. The correct framing is in
[Implications for Task 3](#implications-for-task-3).

---

## Sources found

Every code path that can put a plate string in front of a user:

| # | Source | file:line | Produces |
|---|---|---|---|
| 1 | `ANPREngine.recognize_plate()` → `cv2.dnn_TextRecognitionModel.recognize()` | `ai_engine/intelligence/anpr_engine.py:314` | **The only origin of plate text in the system.** Real CRNN inference. |
| 2 | Video-upload processing → `ANPREvent` (READABLE) | `backend/routes/videos.py:276` | Persists source 1 |
| 3 | Video-upload processing → `ANPREvent` (UNREADABLE, `plate_text=None`) | `backend/routes/videos.py:342` | Null plate, honest |
| 4 | Video-upload processing → `Detection.plate_text` | `backend/routes/videos.py:409` | Persists source 1 |
| 5 | Live-camera processing → `ANPREvent` | `backend/routes/cameras.py:479` | Persists source 1 |
| 6 | WebSocket broadcast of ANPR payloads | `backend/routes/videos.py:320`, `:360` | Relays source 1 |
| 7 | `POST /anpr/test-recognize` | `backend/routes/anpr.py:113`, `:138` | Returns source 1; **does not persist** |
| 8 | `backend/test_anpr.py:183` | hardcoded `KA05MJ4411` @ 92.5 | **Writes to the production DB**; see below |

### Ruled out

| Candidate | Finding |
|---|---|
| `ai_engine/mock_ai.py` | **No plate code whatsoever.** Zero matches for `plate` in 162 lines. Cannot be a source. |
| Frontend mock mode | `VITE_USE_MOCK=false` in `frontend/web_portal/.env`. `mock/mockData.ts` and `mockEngine.ts` contain **no plate strings** — only camera definitions. |
| DB seeds / migrations | `backend/database/init_db.py` only performs `ALTER TABLE ... ADD COLUMN`. It inserts no rows. |

### Source 8 — the one genuine injection path

`backend/test_anpr.py` writes a hardcoded `KA05MJ4411` at 92.5% confidence into the **real
production database** via `SessionLocal()` (`database.database`, not a test fixture DB),
then deletes it at line 213.

It is self-cleaning on success. It is **not** transactional — the write is committed at
line 195 and only removed at line 213, so an assertion failure or crash between those two
points leaves a fabricated plate permanently in the demo dataset.

Verified clean at the time of writing:

```
KA05MJ4411 rows in anpr_events : 0
ids matching 'test-anpr-%'     : 0
```

No residue today. Reported per instruction; not fixed. Worth noting that the risk is real
and one aborted test run away from materialising during a demo.

---

## Reachability

| # | Trigger | Fires in a normal demo? |
|---|---|---|
| 1 | Any vehicle track in any processed frame | **Yes** — unconditional |
| 2–4 | `POST /videos/{id}/process` (the upload-and-analyse flow) | **Yes** — this produced all 147 stored rows |
| 5 | Live camera / webcam processing | Yes, if a camera is started. No stored rows came from it. |
| 6 | Automatic during 2–5 | **Yes** |
| 7 | Manual `POST /anpr/test-recognize` only | Only if someone calls it |
| 8 | `python backend/test_anpr.py` only | Only if someone runs the test suite |

---

## Evidence

All 147 `anpr_events` rows: `camera_id = BOP-07`, `video_id` non-null on every row → **all
came from the video-upload path (source 2/3)**. No live-camera rows, no test residue,
`snapshot_path` null on every row.

Written 2026-09-07 16:07 → 17:47, clustered in two runs (10 rows in the 16:00 hour, 137 in
the 17:00 hour) — consistent with two manual upload-and-process sessions, not with seeding.

### The stored strings are unmistakably CRNN_EN output

75 of 147 rows carry a non-null plate; 30 distinct values:

```
status=UNREADABLE  text=None         n=72     <- honest abstention
status=READABLE    text=KA02HH7256   n=7
status=READABLE    text=SEREARS      n=7
status=READABLE    text=KA02MH7256   n=5
status=READABLE    text=EET1ALLY     n=4
status=READABLE    text=FAEE         n=4
status=READABLE    text=KA02MM005T   n=4
status=READABLE    text=CHEEFES      n=2
status=READABLE    text=LEWESTES     n=2
status=READABLE    text=SAMKUMS      n=2
```

And in `detections` (1095 rows carry plate text):

```
KA02HH7256  236     EET1ALLY  37     THE  34
KA02MH7256  206     FAEE      35     PLNES 31
```

Two things stand out:

1. **`SEREARS`, `CHEEFES`, `LEWESTES`, `EET1ALLY`, `SAMKUMS`, `PLNES`, and the literal
   English word `THE`** are exactly the failure mode the original spec predicted: a model
   trained on English words emitting word-shaped strings from plate glyphs. No mock
   generator would produce these; they are too specifically wrong.
2. **`KA02HH7256` vs `KA02MH7256` vs `KA02MM005T` vs `KAC2MM105T`** — the same physical
   plate read four ways, differing exactly at the letter/digit-confusable positions. That
   is OCR instability, not fabrication.

### Confidence values reconcile against the current code

Running `clean_and_validate_plate_text()` on the stored values reproduces the stored
confidences exactly:

| input | → normalized | conf | status | matches DB |
|---|---|---|---|---|
| `serears` | SEREARS | **80.0** | READABLE | yes (DB: 80.0) |
| `cheefes` | CHEEFES | **80.0** | READABLE | yes |
| `samkums` | SAMKUMS | **80.0** | READABLE | yes |
| `ka02hh7256` | KA02HH7256 | **98.5** | READABLE | yes |
| `eet1ally` | EET1ALLY | **98.0** | READABLE | yes |
| `carns` | CARNS | 70.0 | UNCERTAIN | **no** (DB: 80.0 READABLE) |

29 of 30 distinct values reconcile. The single outlier is `CARNS` — the oldest row in the
table (16:07:42, the only row in that minute), which predates the other 146 by 24 minutes
and most likely comes from an earlier revision of the scorer. Not worth pursuing further;
it does not change the verdict.

Note what those numbers mean: **`SEREARS` — a nonsense word — is stored as a READABLE plate
at 80% confidence, and `EET1ALLY` at 98%.** The score is computed from string shape
(`+18` for containing both letters and digits, `+10` for length 7–10), so a confident-looking
number is attached to a string the model was not confident about. This is the fabricated-confidence
problem in Amendment 01 §C, now with stored values demonstrating it.

---

## Verdict

**Yes — real OCR-produced plate strings have reached the dashboard, and every plate string
in the system is one.** There is no phantom source. `mock_ai.py`, the frontend mock layer,
and the DB initialiser are all conclusively ruled out. The single fabricated-string path
(`test_anpr.py`) has left no residue and did not produce any stored row.

The problem is not that the strings are fake. It is that they are **real, wrong, and
labelled READABLE with a high confidence number that no model produced**. Of 75 non-null
plates, the recognisable ones cluster around a single vehicle read four inconsistent ways,
and the rest are English words. The 72 `UNREADABLE` rows are the system's one honest
behaviour here.

That is a materially worse failure mode than a mock, because a mock is obviously fake at a
glance and `SEREARS @ 80% READABLE` is not — it will be read as a plate by anyone looking
at the dashboard, and it is stored in the same column, with the same status, as a correct
read.

---

## Implications for Task 3

Amendment 02 §E's prescribed framing must be replaced. The baseline is **not**
non-functional. It is functional and inaccurate, which is the harder problem and the one
the rebuild actually addresses. The corrected framing:

> **Baseline status: functional, inaccurate, and dishonestly scored.** The CRNN executes
> under the production OpenCV 5.0.0.93 and returns text for most plate candidates. The text
> is frequently wrong in the manner the spec predicted — English-word-shaped output from a
> model with a language-model prior over `[a-z0-9]`. `exact_match` and `char_accuracy` are
> therefore **real measurements of OCR accuracy**, not measurements of a crash.
>
> `A5 (false-confident rate)` remains **N/A** for the baseline per Amendment 01 §C: the
> confidence attached to each read is a heuristic function of the output string's shape,
> not a model probability, so "confidence ≥ 0.8 and wrong" does not measure what A5 is
> meant to measure. Stored evidence: `SEREARS` @ 80.0 READABLE, `EET1ALLY` @ 98.0 READABLE.

The before/after table in Task 9 can therefore present a genuine accuracy delta. The
rebuild's claim is **not** "we made a dead feature work" — it is "we replaced a feature that
confidently reported wrong plates with one that reports correct plates and abstains when
unsure." The abstention half of that claim is what §7.4 exists to deliver.

**Still blocking for Task 3 (Amendment 02 §B2):** the baseline must be measured in the
reconstructed Python 3.10.11 venv. My OpenCV 4.13 result proves the number is
version-sensitive — running the baseline on the wrong OpenCV would produce `0.0%` and
silently misattribute a crash to OCR error. See `SILENT_FAILURE_AUDIT.md` for the venv
status.
