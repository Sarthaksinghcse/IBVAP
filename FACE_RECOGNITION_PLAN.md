# IBVAP — Robust Facial Recognition & Registry: Implementation Plan

> Scope: harden the existing YuNet + SFace face stack into a production-credible
> recognition subsystem with a proper biometric registry.
> Baseline audited: `ai_engine/intelligence/face_engine.py`, `backend/routes/watchlist.py`,
> `backend/routes/videos.py`, `ai_engine/pipeline.py`, `backend/models/models.py`.
>
> **Revision 2** — reordered after the independent audit in
> [`FACE_AUDIT.md`](./FACE_AUDIT.md). Revision 1 was written from a capability standpoint
> and missed the security findings entirely; the audit's S1 and S2 outrank everything that
> was previously scheduled first. Audit finding IDs (S1, C2, D1…) are cited inline so each
> task traces back to its evidence.

---

## 0. What Actually Exists Today (verified against source)

| Capability | Status | Evidence |
|---|---|---|
| YuNet detect + SFace 128-D embed | Works | `face_engine.py` (forward-pass cleared by `SILENT_FAILURE_AUDIT.md`) |
| Enrollment from one photo | Works | `watchlist.py: register_watchlist_person` |
| Probe test-match endpoint | Works | `watchlist.py: test_face_match` |
| Recognition on **uploaded video** | Works | `videos.py:212-241` |
| Recognition on **live camera** | **Missing** | `pipeline.py` never imports `face_engine` |
| `ThreatEngine.handle_watchlist_match()` | **Dead code** | zero callers repo-wide |
| `FaceRecognitionEvent` table | **Never written** | imported in `watchlist.py`, never instantiated |
| Multi-photo enrollment | Missing | exactly 1 `FaceEmbedding` per person, no add-photo route |
| Threshold calibration | Missing | `0.45` hardcoded in 4 places; SFace canonical is `0.363` |
| Enrollment quality gate | Missing | accepts any photo where a face is found |
| Temporal consensus on match | Missing | one frame becomes a `CRITICAL` alert |
| Embedding index / cache | Missing | JSON re-parsed and brute-forced per job |
| Cache eviction | Bug | `track_face_cache` grows unbounded |
| Snapshot evidence on match | Missing | `snapshot_path` exists in DB, unpopulated |
| Upload path sanitization | **Broken** | audit S1 — arbitrary file write, verified by execution |
| Registry access control | **None** | audit S2/S3 — biometric data served unauthenticated |

**Two headline gaps:**

1. **Security.** The registry is an unauthenticated biometric database with a remote
   arbitrary-file-write in its upload path (S1, S2). This is Phase 0.
2. **Coverage.** Face recognition works on uploaded MP4s and is completely absent from live
   camera feeds — the actual deployment mode. This is Phase 2.

---

## Phase 0 — Security & Concurrency Stop-Gaps (half a day)

*Goal: close the findings that are dangerous today. Nothing else ships first.*

### 0.1 Sanitize the upload path — audit S1 *(Critical)*

`watchlist.py:118` and `videos.py:626` interpolate the client-supplied `file.filename`
straight into a save path. Verified exploitable on Windows: `..\..\..\pwned.jpg` escapes
the storage directory and writes attacker-controlled bytes to an attacker-chosen path.

- Never echo the client filename into a path. Derive it entirely server-side:
  `f"{person_id}{ext}"`, where `ext` comes from an allowlist keyed on the **decoded image**
  (`cv2.imdecode` already runs before the write), not the filename string.
- Keep the original filename in a new `WatchlistPerson.original_filename` column for
  display only — never for I/O.
- Add a shared guard in a new `backend/utils/paths.py`:

```python
def assert_within(path: str, root: str) -> str:
    rp, rr = os.path.realpath(path), os.path.realpath(root)
    if os.path.commonpath([rp, rr]) != rr:
        raise HTTPException(400, "Invalid file path")
    return rp
```

  Call it before every open/write/delete in `watchlist.py` and `videos.py`.

### 0.2 Stop serving the biometric registry publicly — audit S2 *(Critical)*

`main.py:71` mounts the whole storage tree via `StaticFiles`, and `GET /api/watchlist`
hands out every `photo_path` — together, a self-indexing dump of the face database.

- Drop `watchlist/` out of the static mount. Serve photos through
  `GET /api/watchlist/{person_id}/photo`, which streams via `FileResponse` after a
  permission check (a stub returning `True` until 5.3 lands, but the call site exists).
- Do the same for `storage/videos/`. `snapshots/` can stay static for now.
- Update `Watchlist.tsx` to use the new URL.
- Until auth exists, bind to `127.0.0.1` and correct the `--host 0.0.0.0` instruction in
  the setup guide.

### 0.3 Cap the upload — audit S4

`watchlist.py:101` does `await file.read()` with no size limit, buffering the whole upload
in RAM. Reject above ~8 MB and check `content_type` before reading, streaming to a temp
file rather than into memory.

### 0.4 Lock the shared detector — audit C3 *(High)*

`detect_primary_face` calls `setInputSize` / `setScoreThreshold` on a process-wide
singleton while the video worker thread and FastAPI request threads run concurrently — a
check-then-use race on non-thread-safe native state.

- Add `self._lock = threading.Lock()` to `FaceEngine`; wrap the
  set-size → detect → align → feature sequence as one critical section.
- A lock beats thread-local engines here: less memory, and contention is negligible at this
  scale.

**Exit criteria:** a filename of `../../x.jpg` is rejected with 400; watchlist photos 404
on the static path and 200 on the authenticated route; a registration request during an
active video job completes without corrupting either result.

---

## Phase 1 — Correctness Foundation (2 days)

*Goal: make what exists trustworthy and measurable before adding anything.*

### 1.1 Fix the cache — audit C1, C2 *(High)*

Three distinct defects in the same 20 lines of `face_engine.py`:

- **Unbounded growth.** `track_face_cache` never evicts. Add `_evict_stale()` at the top of
  `evaluate_person_track_face()`, cap at 512 entries, evict oldest-first.
- **Key collision (C1).** The key is `camera_id:track_id`; every upload defaults to
  `camera_id="BOP-07"` (`videos.py:637`) and tracker IDs restart at 1 per job on a
  never-cleared singleton — so one video's identity leaks onto another's Track 1. Add a
  per-job scope to the key (`job_id:camera_id:track_id`) and clear that scope in the
  worker's `finally` block. Add `clear_scope(prefix)` alongside `clear_cache()`.
- **Wall-clock TTL (C2).** `cache_ttl_seconds = 2.5` compared against `time.time()` is
  correct for a live camera and wrong for offline analysis, where 2.5 s of wall clock spans
  7–12 s of video timeline. Take an explicit `now` parameter — wall clock from
  `pipeline.py`, `video_time_sec` from `videos.py`.
- **Negative caching.** Cache a `face_detected: False` result for a *much* shorter window
  than a positive one (suggest 0.4 s vs 2.5 s). Today one badly-timed frame catching a
  subject mid-turn suppresses recognition for seconds of footage — the failure most likely
  to spoil a live demo.

> Related, same root cause, outside face scope: `tracker.py`'s `dwell_time` and
> `zone_dwell_time` also use `time.time()`, so loitering thresholds are measured against
> CPU speed rather than video time. Worth fixing in the same commit.

### 1.2 Calibrate the threshold — stop guessing

`0.45` appears in `face_engine.py`, `watchlist.py` (twice), and `videos.py`.

- Create `ai_engine/intelligence/face_config.py`:

```python
SFACE_COSINE_THRESHOLD  = 0.363   # OpenCV Zoo canonical
MATCH_THRESHOLD_STRICT  = 0.45    # low-FP / alerting
MATCH_THRESHOLD_LENIENT = 0.363   # review-queue candidates
MIN_FACE_PX             = 32      # raise from current 16
NEG_CACHE_TTL_S         = 0.4
POS_CACHE_TTL_S         = 2.5
```

- Import it everywhere; delete every literal.
- Build `tests/face_bench/run_bench.py`: point it at a folder of `person_name/*.jpg`,
  compute all genuine vs. impostor pairs, print FAR/FRR/EER and a threshold sweep table.
  Pick the operating point from data, not by feel. Every later accuracy claim is measured
  against this harness.

### 1.3 Write the audit trail

`FaceRecognitionEvent` is dead — imported, never instantiated.

- Add `POST /api/watchlist/events` and `GET /api/watchlist/events` (filter by `person_id`,
  `camera_id`, date range).
- Log **every** evaluation where `face_detected == True` — matches *and* `UNKNOWN_FACE`.
  Unknown-face volume is the only live FAR signal you will have.
- Call it from `videos.py` right after `evaluate_person_track_face`.

### 1.4 Input validation — audit D3, D4, D5

- **D3:** `threat_priority.upper()` is stored unvalidated. `"HGIH"` is accepted, misses
  every `elif` in the severity ladder, and silently becomes **LOW** — a critical target
  demoted by a typo. Make it a Pydantic `Literal["CRITICAL","HIGH","MEDIUM","LOW"]` and
  reject anything else.
- **D4:** `test_face_match`'s `threshold` form field is unvalidated; `0.0` matches the first
  gallery entry against any face and a negative value matches unconditionally. Constrain to
  `[0.2, 0.9]`.
- **D5:** add a unique constraint on `WatchlistPerson.identifier` (nullable) so two records
  cannot both claim `POI-9821`.

### 1.5 Schema and durability — audit I1, I2, I3

- **I1:** `init_db.py:_apply_schema_migrations()` lists columns for `cameras`, `detections`,
  and `alerts` and **nothing for the face tables**, while `create_all()` never adds a column
  to an existing table. Phase 3 and 4 add columns; without entries here they will work on a
  fresh DB and silently not exist on any existing `ibvap.db`. **Add the migration entry in
  the same commit as every model change** — treat this as a standing rule, not a task.
  Also narrow the `except Exception: pass` on line 47 to the duplicate-column case, per the
  prior audit's finding 3.
- **I2:** enable WAL and a busy timeout in `database.py` — a long-running video worker
  otherwise blocks registry writes with `database is locked`:

```python
connect_args={"check_same_thread": False, "timeout": 30}
# + PRAGMA journal_mode=WAL on connect
```

- **I3:** `threat_engine.py` keys `last_alert_times` on `hash(dedup_key)`. Key on the string
  — `hash()` discards information for no benefit and a collision silently suppresses a
  legitimate alert.

### 1.6 Do not delete the dead path

`ThreatEngine.handle_watchlist_match()` has no callers, but Phase 2 needs it. Add a
`# CALLED FROM: pipeline.py (Phase 2)` marker and a smoke test in
`backend/test_face_recognition.py` so it stops silently rotting.

**Exit criteria:** the bench harness prints an EER; every evaluation writes a DB row; cache
stays bounded and job-scoped under a 10-minute soak; two videos processed concurrently
produce no cross-identity leakage.

---

## Phase 2 — Live Camera Recognition (2–3 days)

*Goal: close the coverage gap. Same recognition on RTSP as on MP4.*

> Depends on 1.1. Wiring the live path before the cache is fixed inherits C1 and C2 into
> the deployment mode that matters most.

### 2.1 Give the pipeline a watchlist

`pipeline.py` is a standalone process with no DB session, and must not import SQLAlchemy —
FastAPI stays the only hub, per the architecture rule in the project guide.

- Add `GET /api/watchlist/embeddings` returning the flat record list (`person_id`, `name`,
  `identifier`, `threat_priority`, `embedding`) plus a `version` integer that increments on
  any watchlist write. This endpoint returns biometric templates — put it behind the same
  permission check as 0.2.
- In `pipeline.py`, add a `WatchlistSync` helper: fetch on start, poll
  `GET /api/watchlist/version` every 15 s, refetch only when `version` changes. Fail soft —
  if the backend is down, keep the last known list and log a warning.

### 2.2 Wire the engine into the loop

In `IBVAPPipeline.run()`, between step 2 (tracker) and step 3 (threat engine):

```python
for track in active_tracks:
    if track.object_type != "PERSON":
        continue
    result = face_engine.evaluate_person_track_face(
        frame, track.bbox, self.camera_id, track.track_id,
        self.watchlist.records, now=time.time())
    if result["is_match"]:
        self.threat_engine.handle_watchlist_match(...)   # now live
```

Reuse `handle_watchlist_match` — it already has cooldown and severity rules. Do not
duplicate the logic that `videos.py` inlined; C4 below deletes that duplicate rather than
adding a third copy.

### 2.3 Budget the cost

YuNet + SFace per person per frame will not hold 30 FPS with several tracks.

- Add `face_eval_interval_frames` (default 5): evaluate a given track at most every N
  frames. The positive cache absorbs the rest.
- Early-out on tracks whose bbox height is below `MIN_FACE_PX / 0.15` px — the face is too
  small to embed reliably, so skip before running YuNet.
- Log a `face_ms` field in the existing per-15-frame telemetry line.

**Exit criteria:** a registered face walking past a live webcam raises a `WATCHLIST_MATCH`
alert on the dashboard; FPS drop measured and under 25%.

---

## Phase 3 — Registry Robustness (2–3 days)

*Goal: one photo per person is not a registry. Make enrollment real.*

### 3.1 Multi-photo enrollment

The schema already supports N embeddings per person — the API does not.

- `POST /api/watchlist/{person_id}/photos` — add a photo, run the quality gate, append a
  `FaceEmbedding` row.
- `DELETE /api/watchlist/{person_id}/photos/{embedding_id}`.
- `WatchlistPerson.photo_path` becomes the *primary* photo; add `FaceEmbedding.photo_path`
  for the rest. **Add the `init_db.py` migration entry in the same commit (I1).**
- Accept multi-file upload on the create route (`file: List[UploadFile]`), keeping the
  single-file form backward compatible. Apply 0.1 and 0.3 to every new upload path.

### 3.2 Quality gate at enrollment

Reject bad enrollments instead of poisoning the gallery. New
`face_engine.assess_quality(img, face_info) -> (ok, score, reason)`:

| Check | Rule |
|---|---|
| Face size | `w >= 80px` and `h >= 80px` in the source photo |
| Sharpness | Laplacian variance `>= 60` (blur reject) |
| Brightness | mean luma within `[50, 205]` |
| Pose | landmark symmetry — eye-to-nose L/R ratio within `0.65–1.55` |
| Uniqueness | face count in photo `== 1` (ambiguous group photos rejected) |

Return the score to the UI so the operator sees *why* a photo was refused.

### 3.3 Duplicate-enrollment guard

Before saving, match the new embedding against the whole active gallery at
`MATCH_THRESHOLD_STRICT`. On a hit, return `409` with "This face is already registered as
{name}. Add as an additional photo?" and let the operator confirm or redirect to `/photos`.

### 3.4 Matching against multi-embedding galleries

`match_against_watchlist` currently treats every embedding as an independent record, so a
person with 5 photos gets 5 shots at the threshold — which inflates FAR.

- Group records by `person_id`.
- Per person, score = **max** cosine across their embeddings.
- Require the second-best *person* to trail by a margin (`>= 0.05`), otherwise return
  `AMBIGUOUS` rather than a match.
- Return the top-3 candidates in the response for operator review.
- Re-run the 1.2 bench after this change — grouping shifts the operating point.

**Exit criteria:** a person can hold 5 photos; a blurry photo is refused with a stated
reason; re-registering the same face is caught; EER improves versus the Phase 1 baseline.

---

## Phase 4 — Match Reliability & Presentation (2 days)

*Goal: stop single frames from firing CRITICAL alerts, and stop correct matches from
looking like guesses.*

### 4.1 Temporal consensus

ANPR already does this (`anpr_engine.py` multi-frame consensus). Mirror it.

- New `FaceTrackAccumulator` in `face_engine.py`, keyed by the job-scoped cache key from
  1.1, holding a deque of the last 7 per-frame results.
- Confirm a match only when the **same** `person_id` wins `>= 3` of the last 5 evaluations.
  Report the median similarity, not the peak.
- Emit a `CANDIDATE` state at 2/5 — shown in the UI, not alerted on.
- This replaces cache-first-result-wins, which locks in the first (possibly wrong) answer.

### 4.2 Snapshot evidence (also closes roadmap F4)

- On a confirmed match, write the annotated frame to `storage/snapshots/{alert_id}.jpg` and
  set `Alert.snapshot_path`.
- Also crop and store the matched face at `storage/snapshots/faces/{event_id}.jpg`,
  referenced from `FaceRecognitionEvent` (add a `snapshot_path` column — **and its
  migration entry, I1**).
- Without evidence an operator cannot dispute a false match. Highest-value item in the phase.

### 4.3 Delete the duplicated alert path — audit C4

`videos.py:225` reimplements watchlist alerting inline, with only a permanent
`alerted_tracks` set and **no cooldown**. Because its key includes `track_id`, every
re-identification of the same person — which the IoU/centroid tracker does readily under
occlusion — mints a fresh key and fires another CRITICAL alert.

- Delete the inline block; call `threat_engine.handle_watchlist_match()` (live since 2.2).
- One implementation, one cooldown, one severity ladder. This is duplicated-logic drift,
  not a missing feature.

### 4.4 Fix the similarity display — audit D1

`similarity` is raw cosine × 100, so the *weakest accepted match* renders as **45%** and a
strong one as 60–70%. `Watchlist.tsx:770` shows it, and `videos.py:240` writes it into the
alert text: *"…with 45.2% face match similarity"* on a CRITICAL alert. Correct internally,
but it reads as a coin flip to an operator or a judge.

- Keep raw cosine in the DB (`cosine_score` already exists).
- Display a calibrated confidence: piecewise-linear so the decision threshold maps to 50%
  and the genuine-pair median from the 1.2 bench maps to ~95%.
- Label the raw figure "cosine" wherever both are shown.

### 4.5 Separate the confidence scales — audit D2

`Alert.confidence` receives YOLO confidence (0–100) on detection alerts and cosine×100 on
watchlist alerts — two meanings in one column, so any aggregate over it is meaningless. Add
`Alert.confidence_kind` (`DETECTION` | `FACE_MATCH`), or a separate `match_confidence`
column, and fix the Analytics aggregation accordingly.

### 4.6 Low-light path

Reuse the CLAHE work already in `anpr_engine.py`: when mean frame luma `< 60`, apply CLAHE
to the head crop before YuNet. Measure on the 1.2 bench first — if it does not improve night
EER, leave it off.

**Exit criteria:** a one-frame false hit no longer alerts; every alert has a viewable
snapshot; a confirmed match displays a confidence an operator will believe.

---

## Phase 5 — Registry UX & Governance (2–3 days)

*Goal: it is a biometric database. Treat it as one.*

### 5.1 `Watchlist.tsx` upgrades

- Photo gallery per person (add / remove / set primary), with the quality score badge on
  each photo.
- **Match history tab** per person, backed by `GET /api/watchlist/events`: camera,
  timestamp, similarity, snapshot thumbnail.
- The test-match modal already has a threshold slider — extend it to show the top-3
  candidate list from 3.4, not just the winner.
- Bulk import: a CSV (`name,identifier,priority`) plus a folder of photos matched by
  filename, with a dry-run preview of accept/reject per row. Filenames here are data, never
  paths (0.1).

### 5.2 Unknown-face review queue

New page. Unmatched faces that clear the quality gate get clustered by embedding proximity
(greedy agglomerative at `0.55` cosine) and shown as "Unidentified subject seen 7x at
BOP-07". One click promotes a cluster into a registry entry — this is how a watchlist
actually grows in the field.

### 5.3 Authentication and governance — audit S3

Roadmap F12 files RBAC as "Lower Priority". For a biometric registry that ordering is
wrong: today `DELETE /api/watchlist/{id}` permanently destroys a person's record for anyone
who can reach port 8000. Promote it here.

- Real auth on the API; three roles (admin, operator, viewer). Registry writes are
  admin-only. Fill in the permission stub from 0.2.
- `WatchlistAuditLog` model: `actor`, `action` (CREATE/UPDATE/DELETE/EXPORT), `person_id`,
  `timestamp`, `justification` (required free text on delete).
- Retention: `UNKNOWN_FACE` rows in `FaceRecognitionEvent` auto-purge after N days
  (configurable, default 30). Confirmed matches are kept.

**Exit criteria:** unauthenticated requests to registry routes return 401; every mutation is
logged with a reason; unknown faces cluster into promotable candidates.

---

## Phase 6 — Scale & Accuracy Ceiling (post-hackathon)

| # | Item | Why |
|---|---|---|
| 6.1 | **FAISS / hnswlib index** | Brute-force numpy is fine to ~500 embeddings, not 50k. Build an in-process index in the backend, rebuilt on `version` bump. |
| 6.2 | **Binary embedding storage** | `embedding_json` as TEXT re-parses on every load. Move to `LargeBinary` float32 blobs — roughly 10x faster gallery load. |
| 6.3 | **Stronger recogniser** | SFace is fast but dated. Benchmark ArcFace / AdaFace ONNX against the 1.2 harness before swapping; keep the same interface. |
| 6.4 | **Forward-pass readiness checks** | Per `SILENT_FAILURE_AUDIT.md`: `FaceEngine.is_ready` proves construction, not inference. Verify one real forward pass with a canned input at load time. |
| 6.5 | **Face-aware tracking (pairs with F2)** | Once ByteTrack lands, use confirmed face identity to stitch tracks across occlusion — identity survives a track ID change. |
| 6.6 | **Cross-camera identity (pairs with F7)** | Same embedding at BOP-07 then BOP-09 becomes one subject with a direction vector. |
| 6.7 | **Liveness / spoof check** | A printed photo currently matches. Minimum viable: reject faces with near-zero inter-frame texture variance. |
| 6.8 | **Encryption at rest** | Biometric templates and photos in plaintext SQLite/disk. Follows 5.3, not before. |

---

## Sequencing Summary

```
Phase 0  Security       -- S1/S2/S4/C3; half a day; nothing ships before it
   |
Phase 1  Correctness    -- cache, calibration, audit trail, validation, schema
   |                       everything later is measured against its bench
Phase 2  Live pipeline  -- highest user-visible value; needs 1.1 first
   |
Phase 3  Registry depth -- multi-photo + quality gate; biggest accuracy win per hour
   |
Phase 4  Reliability    -- consensus, snapshots, dedup, honest confidence
   |
Phase 5  UX + auth      -- makes it operable and defensible
   |
Phase 6  Scale          -- only once the above is measured and stable
```

**Minimum credible demo path: Phase 0 + Phase 1 + Phase 2 + 4.1 + 4.2 + 4.4.**
Roughly a week and a half. Covers live recognition, no false CRITICALs, evidence attached
to every alert, a confidence figure that reads as credible, and no open biometric database.

**If only three things get fixed:** S1 (remote arbitrary file write), S2 (open biometric
database), C2 (negative cache silently discarding seconds of footage — the failure most
likely to spoil a live demo).

## Files Touched, by Phase

| File | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `ai_engine/intelligence/face_engine.py` | x | x | x | x | x | | x |
| `ai_engine/intelligence/face_config.py` *(new)* | | x | | x | x | | |
| `ai_engine/pipeline.py` | | | x | | x | | |
| `ai_engine/intelligence/threat_engine.py` | | x | x | | x | | |
| `ai_engine/tracking/tracker.py` | | x | | | | | x |
| `backend/main.py` | x | | | | | x | |
| `backend/utils/paths.py` *(new)* | x | | | x | | | |
| `backend/routes/watchlist.py` | x | x | x | x | x | x | x |
| `backend/routes/videos.py` | x | x | | x | x | | |
| `backend/models/models.py` | x | x | | x | x | x | x |
| `backend/schemas/schemas.py` | | x | x | x | x | x | |
| `backend/database/init_db.py` | | x | | x | x | x | |
| `backend/database/database.py` | | x | | | | | |
| `frontend/web_portal/src/pages/Watchlist.tsx` | x | | | x | x | x | |
| `frontend/web_portal/src/pages/FaceReview.tsx` *(new)* | | | | | | x | |
| `tests/face_bench/` *(new)* | | x | | x | x | | x |
