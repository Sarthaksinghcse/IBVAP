# IBVAP — Independent Audit: Facial Recognition & Watchlist Registry

> Scope: the face subsystem as integrated, end to end — engine, registry API, storage,
> video worker, DB, frontend. Read directly from source; one finding verified by execution.
>
> **Relationship to `SILENT_FAILURE_AUDIT.md`:** that audit examined *model forward-pass
> correctness* and cleared YuNet/SFace ("no defect found"). This audit does not dispute
> that — the models are fine. Every finding below is at the **integration, data, and
> access-control** layer, which the earlier audit explicitly did not cover.

---

## Severity Summary

| ID | Finding | Severity |
|---|---|---|
| S1 | Unauthenticated arbitrary file write via upload filename (**verified by execution**) | **Critical** |
| S2 | Biometric photos served unauthenticated at `/storage/watchlist/` | **Critical** |
| S3 | No authentication or authorization on any registry endpoint | **High** |
| S4 | Unbounded in-memory read of uploaded photo (DoS) | Medium |
| C1 | Face cache keyed on `camera_id:track_id` — collides across videos | **High** |
| C2 | Cache TTL is wall-clock, applied to non-real-time video analysis | **High** |
| C3 | Shared mutable OpenCV detector across threads — data race | **High** |
| C4 | No alert cooldown on the video path; re-ID causes duplicate CRITICALs | Medium |
| D1 | `similarity` reports raw cosine × 100 — a confirmed match displays as "45%" | Medium |
| D2 | `Alert.confidence` mixes two incompatible scales | Low |
| D3 | `threat_priority` accepts any string; typos silently degrade to LOW | Medium |
| D4 | `threshold` form field unvalidated — `threshold=0` matches everyone | Medium |
| D5 | `identifier` not unique; duplicate POIs permitted | Low |
| I1 | No migration entries for face tables — planned columns will silently not apply | Medium |
| I2 | SQLite in rollback-journal mode + long-running writer thread → lock contention | Medium |
| I3 | `hash(dedup_key)` used as a dict key — lossy, collision suppresses alerts | Low |

---

## S1 — Unauthenticated Arbitrary File Write *(Critical — verified)*

`backend/routes/watchlist.py:118-122`

```python
safe_filename = f"{person_id[:8]}_{file.filename}"
file_path = os.path.join(STORAGE_DIR, safe_filename)
with open(file_path, "wb") as f:
    f.write(contents)
```

`file.filename` is attacker-controlled and never sanitized. The variable is *named*
`safe_filename`, but nothing makes it safe. The `{person_id[:8]}_` prefix looks like it
would neutralize a leading `..`, and on Linux it mostly would — a nonexistent intermediate
directory stops POSIX path resolution. **On Windows it does not**, because Win32 collapses
`..` lexically before touching the filesystem, so the prefixed first component is simply
popped along with the rest.

I reproduced the exact line in isolation on this machine:

| Uploaded `filename` | Result |
|---|---|
| `..\..\..\pwned.jpg` | wrote outside `storage/watchlist/` |
| `../../../pwned2.jpg` | wrote outside `storage/watchlist/` |
| `x\..\..\..\pwned3.jpg` | wrote two levels above `storage/` |

All three escaped the storage directory. Depth is chosen by the attacker, and the file
*contents* are the raw uploaded bytes — so this is arbitrary-path, arbitrary-content write
by an unauthenticated caller. Overwriting `backend/ibvap.db` or dropping a `.py` file onto
the import path both follow directly.

`backend/routes/videos.py:626` has the identical pattern (`f"{video_id}_{file.filename}"`).
The `DELETE` route inherits the same tainted value back out of the DB.

**Fix:** never echo the client filename into a path. Derive the name entirely server-side —
`f"{person_id}{ext}"` where `ext` is validated against an allowlist taken from the *decoded
image*, not from the filename. Then assert
`os.path.commonpath([os.path.realpath(path), STORAGE_DIR]) == STORAGE_DIR` before writing.
This is a two-line fix and should land before anything else in the plan.

---

## S2 — Biometric Photos Served Without Authentication *(Critical)*

`backend/main.py:71` mounts the whole storage tree publicly:

```python
app.mount("/storage", StaticFiles(directory=STORAGE_ROOT), name="storage")
```

`GET /api/watchlist` (also unauthenticated) returns every `photo_path`, so the two together
are a complete, self-indexing dump of the face database: enumerate the registry, then fetch
each photo. Same exposure applies to `storage/videos/` — full uploaded surveillance footage.

For a border-security system this is the finding with the worst consequences outside a
demo. A watchlist is a list of people the state considers suspect; publishing it discloses
who is under surveillance, and the photos are biometric identifiers that cannot be reissued
like a password.

**Fix:** serve watchlist and video media through an authenticated route that checks
permission and streams the file, not `StaticFiles`. If auth genuinely cannot land before
the demo, at minimum bind the server to `127.0.0.1` and say so in the README, rather than
`--host 0.0.0.0` as the setup guide currently instructs.

---

## S3 / S4 — Access Control and Upload Limits

- **S3:** no auth on any endpoint. `DELETE /api/watchlist/{id}` permanently destroys a
  person's biometric record for anyone who can reach port 8000. Roadmap item F12 (RBAC) is
  filed as "Lower Priority" — for a biometric registry that ordering is wrong.
- **S4:** `contents = await file.read()` (`watchlist.py:101`) buffers the entire upload in
  RAM with no size cap and no content-type check. A single large POST exhausts memory. The
  video route correctly uses `shutil.copyfileobj`; the watchlist route should cap at a few
  MB and reject before reading.

---

## C1 — Cache Key Collides Across Videos *(High)*

`face_engine.py:212` — `cache_key = f"{camera_id}:{track_id}"`.

`videos.py:637` defaults every upload to `assigned_camera = camera_id or "BOP-07"`, and
`Tracker` restarts IDs from 1 for each job. The engine is a process-wide singleton whose
cache is never cleared between jobs. So video A's "Track 1 = Rajesh, 61% match" is still
sitting in the cache when video B's Track 1 is evaluated — and within the TTL, **video B's
unrelated person inherits video A's identity**. Uploads are processed in daemon threads
with no serialization, so two concurrent jobs collide continuously.

**Fix:** include `video_id` (or a per-job UUID) in the key, and clear the job's keys in the
worker's `finally` block. A per-job engine handle would be cleaner than the singleton.

---

## C2 — Wall-Clock TTL on Non-Real-Time Analysis *(High)*

`face_engine.py:195` sets `cache_ttl_seconds = 2.5` and compares against `time.time()`.
That is correct for a live camera. The video worker is not a live camera: it samples at
5 analysis-FPS and runs as fast as the CPU allows. At a realistic 15–25 analysis-frames per
wall-clock second, 2.5 s of wall clock covers roughly **7–12 seconds of video timeline**.

The damaging direction is the negative cache. If the sampled frame catches a subject
mid-turn, `{"face_detected": False}` is cached and reused for the next ~10 seconds of
footage — during which the subject may be facing the camera the entire time. A watchlist
target can walk through the whole clip unmatched because of one badly-timed frame. This
plausibly explains any "the face engine sometimes just doesn't see them" behaviour.

The same wall-clock-in-offline-analysis mistake exists in `tracker.py` (`dwell_time` and
`zone_dwell_time` use `time.time()`), so loitering thresholds are also measured against
processing speed rather than video time. Out of face scope, but the same root cause and
worth fixing together.

**Fix:** pass an explicit `now` into the engine — wall clock for live, `video_time_sec` for
offline — instead of calling `time.time()` internally. Cache negatives far more briefly
than positives.

---

## C3 — Shared Mutable Detector Across Threads *(High)*

`detect_primary_face` mutates shared state on every call:

```python
self.detector.setInputSize((w, h))
self.detector.setScoreThreshold(score_threshold)
_, faces = self.detector.detect(img_bgr)
```

`FaceEngine` is a singleton; the video worker runs in a `threading.Thread` while FastAPI
serves `POST /api/watchlist` and `/test-match` concurrently. `cv2.FaceDetectorYN` is not
documented as thread-safe, and this is a textbook check-then-use race: thread A sets the
input size for a 64×80 crop, thread B sets it for a 1920×1080 photo, thread A calls
`detect`. Best case garbage detections; worst case a native-level crash that takes the
whole backend down.

**Fix:** a `threading.Lock` around the detect/extract critical section, or thread-local
engine instances. A lock is the smaller change and the contention is acceptable at this
scale.

---

## C4 — No Cooldown on the Video Alert Path *(Medium)*

`ThreatEngine.handle_watchlist_match()` implements dedup via
`alert_cooldown_seconds` — and has **zero callers**. `videos.py:225` reimplemented the
logic inline with only a permanent `alerted_tracks` set keyed
`watchlist_{person_id}_{track_id}`.

Because the key includes `track_id`, every re-identification of the same person — which the
IoU/centroid tracker does readily under occlusion — mints a fresh key and fires another
CRITICAL alert for the same individual. There is no cooldown and no consensus, so a single
false positive frame is sufficient. The correct implementation already exists and is
unused; this is duplicated-logic drift, not a missing feature.

---

## D1 — "45% Match" on a Confirmed Match *(Medium)*

`face_engine.py:183` — `similarity_pct = best_score * 100.0`, i.e. raw cosine rescaled.
The match threshold is cosine `0.45`. So the *weakest accepted match* displays as **45%**
and a strong one as roughly 60–70%.

`Watchlist.tsx:770` renders `Similarity: 45.2%`, and `videos.py:240` writes it into the
alert text: *"WATCHLIST MATCH … with 45.2% face match similarity."* An operator — or an SIH
judge — reading "45% similarity" on a CRITICAL alert will reasonably conclude the system is
guessing. It is not a correctness bug; it is a credibility bug, and it is cheap to fix.

**Fix:** keep raw cosine in the DB, and display a calibrated confidence that maps the
decision threshold to a meaningful figure (e.g. piecewise-linear so threshold → 50% and the
observed genuine-pair median → ~95%). Derive the mapping from the benchmark harness, and
label the raw number "cosine" wherever it is shown alongside.

---

## D2–D5 — Validation Gaps

- **D2:** `Alert.confidence` receives YOLO confidence (0–100) on detection alerts and
  cosine×100 on watchlist alerts. Two different meanings in one column; any aggregate over
  it is meaningless.
- **D3:** `threat_priority.upper()` is stored with no validation. `"HGIH"` is accepted, then
  fails every `elif` in the severity ladder and silently becomes **LOW** — a critical target
  demoted by a typo. Use an enum, reject anything else.
- **D4:** `test_face_match` accepts `threshold` as an unvalidated float. `threshold=0.0`
  matches the first person in the gallery against any face; a negative value matches
  unconditionally. Constrain to `[0.2, 0.9]`.
- **D5:** `identifier` (the POI number) is indexed but not unique — two records can claim
  `POI-9821`. Add a unique constraint, nullable.

---

## I1 — Migrations Will Not Cover the Planned Face Columns *(Medium)*

`init_db.py:_apply_schema_migrations()` lists columns for `cameras`, `detections`, and
`alerts` — **nothing for the face tables**. `Base.metadata.create_all()` creates missing
*tables* but never adds a column to an existing one.

This is currently latent, but it is a live trap for the plan: `FaceEmbedding.photo_path`
(Phase 3) and `FaceRecognitionEvent.snapshot_path` (Phase 4) will appear to work on a fresh
DB and silently not exist on any developer's or judge's existing `ibvap.db`. The failure
surfaces as `OperationalError: no such column` at runtime, or worse gets swallowed by the
`except Exception: pass` on line 47 that the prior audit already flagged.

**Fix:** add the migration entries in the same commit as the model change, every time.

---

## I2 / I3 — Durability and Dedup

- **I2:** `check_same_thread=False`, default rollback-journal mode, no `busy_timeout`, no
  WAL. A long-running video worker committing frequently will block registry writes from the
  HTTP thread; the operator sees `database is locked`. Enable WAL and set a busy timeout —
  a two-line change in `database.py`.
- **I3:** `threat_engine.py` uses `self.last_alert_times[hash(dedup_key)]` rather than the
  string itself. `hash()` discards information for no benefit; a collision silently
  suppresses a legitimate alert. Key on the string.

---

## What the Audit Changes About the Plan

`FACE_RECOGNITION_PLAN.md` was written from a capability standpoint and **missed the
security findings entirely** — S1 and S2 are more urgent than anything currently in Phase 1,
and neither appears in it. Revised ordering:

| | Was | Should be |
|---|---|---|
| **Phase 0** *(new)* | — | S1, S2, S4, C3 — filename sanitization, authenticated media, upload cap, detector lock. Half a day. |
| **Phase 1** | cache eviction, threshold bench, audit trail | unchanged, **plus** C1, C2 (cache keying and time source), D3, D4 (validation), I1, I2 |
| **Phase 2** | live pipeline | unchanged — but C1/C2 must be fixed first or the live path inherits both |
| **Phase 3** | registry depth | unchanged |
| **Phase 4** | consensus + snapshots | **plus** C4 (delete the duplicated inline path, call `handle_watchlist_match`) and D1 (similarity display) |
| **Phase 5** | UX + governance | S3/RBAC promoted from roadmap F12 into this phase |

**Corrected minimum credible demo path: Phase 0 + Phase 1 + Phase 2 + 4.1 + 4.2 + D1.**

The three findings I would fix today regardless of schedule: **S1** (remote arbitrary file
write), **S2** (open biometric database), and **C2** (negative cache silently discarding
seconds of footage — the one most likely to make a live demo fail).
