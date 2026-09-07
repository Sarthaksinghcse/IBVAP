# ANPR Benchmark Set

This directory is the measuring instrument for the ANPR rebuild. Every accuracy
claim in `ANPR_BASELINE.md` and `ANPR_REBUILD_REPORT.md` comes from here.

## Running it

```bash
# Baseline: the frozen pre-rebuild engine (morphological localisation + CRNN_EN)
python tests/anpr_bench/run_bench.py --engine current --out tests/anpr_bench/baseline.csv

# The rebuilt engine
python tests/anpr_bench/run_bench.py --engine new --out tests/anpr_bench/task6.csv
```

Each run writes two files:

- `<out>` — the per-bucket summary table
- `<out>.per_image.csv` (e.g. `baseline.per_image.csv`) — one row per image, with
  the predicted string next to the true one. This is the file you read when a
  number looks wrong.

`--engine current` loads `legacy_engine.py`, a frozen verbatim copy of the engine
at the `baseline` commit. It stays runnable after Task 6 rewrites the live engine
in place, so before/after can be re-measured at any time rather than trusting a
stale CSV.

## Metrics

| Metric | Definition |
|---|---|
| `detect_recall` | fraction of images where a plate bbox was returned |
| `exact_match` | fraction where the predicted string equals `true_plate` exactly |
| `char_accuracy` | mean of `1 - levenshtein(pred, true) / max(len(pred), len(true))` |
| `false_confident` | fraction emitted with confidence >= 0.8 **and** wrong |
| `mean_latency_ms` | mean wall-clock ms per image |

All fractions use the bucket's full image count as the denominator, so a bucket
where the engine detects nothing scores 0 rather than being excluded.

### Two caveats on the baseline numbers

**1. Baseline confidence is not a probability.** The pre-rebuild engine's
confidence is a heuristic score computed from string shape, not model output.
`false_confident` is therefore **not meaningful** for `--engine current` and is
reported as `N/A` in `ANPR_BASELINE.md`.

**2. The baseline CRNN never actually executes.** Verified on OpenCV 4.13.0 and
expected to hold on the 5.0.0.93 in the project venv:
`text_recognition_CRNN_EN_2021sep.onnx` has a single-channel first convolution
(`blobs[0] = [64, 1, 3, 3]`), but `recognize_plate()` feeds it a 3-channel BGR
image on all four of its passes (`cv2.cvtColor(..., COLOR_GRAY2BGR)`), producing
an input blob of `[1, 3, 32, 100]`. Every `model.recognize()` call raises

```
(-215:Assertion failed) ngroups > 0 && inpCn % ngroups == 0 && outCn % ngroups == 0
```

which the `except Exception: pass` inside the per-pass loop swallows silently.
The engine therefore returns `UNREADABLE` for every input, and `is_ready` still
reports `True` because the failure happens at `forward()`, not at `readNet()`.

The same model returns a string when fed a 1-channel array, so this is an input
plumbing bug, not a corrupt model file.

**This is left unfixed on purpose.** The baseline must record what the deployed
system actually does, and what it actually does is read zero plates. But it means
a `0.0%` baseline `exact_match` measures a crash, **not** the CRNN language-model
bias described in the spec's problem statement. Any before/after comparison must
say so, or the rebuild takes credit for fixing something that was never measured.

## HUMAN GATE 1 — what needs collecting

**This is the current blocker.** Nothing downstream can produce a number without it.

Put images in `images/<bucket>/` and add one row per image to `ground_truth.csv`.

| Folder | Target | How to get it |
|---|---|---|
| `clean_frontal` | 40 | Phone photos in a parking lot, straight on. ~40 min. |
| `angled` | 30 | Same session, walk 20-45 degrees off axis. |
| `low_light` | 25 | Same location at dusk, or under sodium lighting. |
| `motion_blur` | 25 | 10 min of roadside video, extract frames with `ffmpeg -i clip.mp4 -vf fps=2 out_%04d.jpg` |
| `dirty_occluded` | 20 | Hardest bucket. Commercial vehicles and truck yards are the best source. |

**Minimum to unblock Task 3: 100 rows total, with `clean_frontal` at 30 or more.**

### Do not pad a short bucket

If a bucket cannot reach its target, **reduce it and record the actual count** in
`ANPR_BASELINE.md`. Do not fill it with duplicates, crops of the same vehicle, or
synthetic augmentation. Nine real images with the sample size stated is honest
data; twenty images where eleven are rotations of one plate silently invalidates
the entire benchmark and every conclusion drawn from it.

The set must reflect the conditions you will actually demo in.

## ground_truth.csv format

```csv
filename,bucket,true_plate
0001.jpg,clean_frontal,HR26DK8337
0002.jpg,angled,DL8CAA1234
0003.jpg,low_light,MH12AB1234
```

- `filename` is the bare filename; the harness looks for it at
  `images/<bucket>/<filename>`.
- `bucket` must be one of the five folder names above.
- `true_plate` is uppercase with no spaces, dashes, or `IND` prefix.

Rows that are incomplete or name an unknown bucket are skipped with a warning.
Rows whose image file is missing are reported and excluded from the metrics, and
the run prints a warning saying how many images the numbers actually cover — so a
partially-collected set can never quietly masquerade as a full one.

## Why images are not committed

`storage/` is gitignored but this directory is not, so benchmark images **are**
tracked. Keep them small (resize to <= 1280px on the long edge). If the set grows
past a few hundred MB, move it to external storage and document the location here.
