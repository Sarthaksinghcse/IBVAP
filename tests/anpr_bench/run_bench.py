#!/usr/bin/env python3
"""
IBVAP ANPR benchmark harness.

Runs an ANPR engine over a labelled image set and reports per-bucket and overall
accuracy. Exists so that "the rebuild improved things" is a number, not an opinion.

    python tests/anpr_bench/run_bench.py --engine current --out tests/anpr_bench/baseline.csv
    python tests/anpr_bench/run_bench.py --engine new     --out tests/anpr_bench/final.csv

Engine selection:
    current -> tests/anpr_bench/legacy_engine.py (frozen pre-rebuild snapshot)
    new     -> ai_engine/intelligence/anpr_engine.py (the live engine)

Interface notes (see AMENDMENT 01 section B3 - the engine interface is frozen):
  * vehicle_bbox is in PERCENT of frame, so a full-image run is w=100, h=100.
  * plate_confidence comes back on a 0-100 scale and is divided by 100 here,
    at the harness boundary, before any threshold is applied.
  * force_refresh=True defeats the engine's per-track result cache.
  * Each image gets a unique track_id so per-track temporal consensus cannot
    leak state between unrelated images.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import sys
import time
from typing import Any, Dict, List, Tuple

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(BENCH_DIR))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

BUCKETS = ["clean_frontal", "angled", "low_light", "motion_blur", "dirty_occluded"]

# Confidence at or above which a wrong answer counts as "false confident".
# 0.8 on the 0-1 scale; the harness has already divided by 100 by this point.
FALSE_CONFIDENT_THRESHOLD = 0.80

FULL_FRAME_BBOX = {"x": 0.0, "y": 0.0, "w": 100.0, "h": 100.0}
BENCH_CAMERA_ID = "BENCH"

METRIC_FIELDS = [
    "bucket", "n", "detect_recall", "exact_match",
    "char_accuracy", "false_confident", "mean_latency_ms",
]


# --------------------------------------------------------------------------
# Levenshtein (two-row DP). Deliberately hand-rolled: not worth a dependency.
# --------------------------------------------------------------------------
def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(
                prev[j] + 1,                 # deletion
                cur[j - 1] + 1,              # insertion
                prev[j - 1] + (ca != cb),    # substitution
            ))
        prev = cur
    return prev[-1]


def char_accuracy(pred: str, true: str) -> float:
    """1 - normalised edit distance. Empty prediction against a real plate = 0.0."""
    if not true:
        return 0.0
    denom = max(len(pred), len(true))
    if denom == 0:
        return 0.0
    return 1.0 - (levenshtein(pred, true) / denom)


# --------------------------------------------------------------------------
# Engine loading
# --------------------------------------------------------------------------
def load_engine(kind: str):
    """Return an object exposing evaluate_vehicle_plate(...)."""
    if kind == "current":
        legacy_path = os.path.join(BENCH_DIR, "legacy_engine.py")
        if not os.path.exists(legacy_path):
            raise FileNotFoundError(
                "Frozen baseline engine missing at " + legacy_path + ". Restore it with: "
                "git show baseline:ai_engine/intelligence/anpr_engine.py"
            )
        spec = importlib.util.spec_from_file_location("anpr_legacy_engine", legacy_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["anpr_legacy_engine"] = module
        spec.loader.exec_module(module)
    elif kind == "new":
        import ai_engine.intelligence.anpr_engine as module  # noqa: F401
    else:
        raise ValueError("unknown engine kind: " + str(kind))

    # Prefer a clean instance when the engine supports it (amendment section B4).
    engine_cls = getattr(module, "ANPREngine", None)
    if engine_cls is not None and hasattr(engine_cls, "reset_instance"):
        engine_cls.reset_instance()
    return module.get_anpr_engine()


# --------------------------------------------------------------------------
# Ground truth
# --------------------------------------------------------------------------
def load_ground_truth(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        raise FileNotFoundError("ground truth missing at " + path)
    rows: List[Dict[str, str]] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"filename", "bucket", "true_plate"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                path + " is missing column(s): " + ", ".join(sorted(missing))
                + ". Expected header: filename,bucket,true_plate"
            )
        for lineno, row in enumerate(reader, start=2):
            fn = (row.get("filename") or "").strip()
            bucket = (row.get("bucket") or "").strip()
            plate = (row.get("true_plate") or "").strip().upper()
            if not fn and not bucket and not plate:
                continue  # blank line
            if not (fn and bucket and plate):
                print("  ! " + path + ":" + str(lineno) + ": incomplete row, skipped")
                continue
            if bucket not in BUCKETS:
                print("  ! " + path + ":" + str(lineno) + ": unknown bucket '" + bucket + "', skipped")
                continue
            rows.append({"filename": fn, "bucket": bucket, "true_plate": plate})
    return rows


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------
def evaluate(engine, rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    import cv2

    results: List[Dict[str, Any]] = []
    missing_files: List[str] = []

    for idx, row in enumerate(rows):
        img_path = os.path.join(BENCH_DIR, "images", row["bucket"], row["filename"])
        if not os.path.exists(img_path):
            missing_files.append(os.path.relpath(img_path, REPO_ROOT))
            continue
        frame = cv2.imread(img_path)
        if frame is None:
            missing_files.append(os.path.relpath(img_path, REPO_ROOT) + " (unreadable)")
            continue

        t0 = time.perf_counter()
        try:
            res = engine.evaluate_vehicle_plate(
                frame_bgr=frame,
                vehicle_bbox=dict(FULL_FRAME_BBOX),
                camera_id=BENCH_CAMERA_ID,
                track_id=idx,               # unique per image: no consensus bleed
                vehicle_type="CAR",
                force_refresh=True,         # defeat the per-track cache
            )
        except Exception as exc:  # a crash on one image must not lose the whole run
            print("  ! engine raised on " + row["bucket"] + "/" + row["filename"] + ": " + repr(exc))
            res = {}
        latency_ms = (time.perf_counter() - t0) * 1000.0

        pred = (res.get("plate_text") or "").strip().upper()
        raw_conf = res.get("plate_confidence")
        # Boundary conversion: engine returns 0-100, everything below is 0-1.
        conf = (float(raw_conf) / 100.0) if raw_conf is not None else 0.0
        detected = res.get("plate_bbox") is not None

        results.append({
            "filename": row["filename"],
            "bucket": row["bucket"],
            "true_plate": row["true_plate"],
            "pred_plate": pred,
            "confidence": conf,
            "detected": detected,
            "exact": pred == row["true_plate"],
            "char_acc": char_accuracy(pred, row["true_plate"]),
            "latency_ms": latency_ms,
            "status": res.get("plate_status"),
        })

    return results, missing_files


def aggregate(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-bucket rows in fixed bucket order, then an OVERALL row."""
    def summarise(label: str, rs: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(rs)
        if n == 0:
            return {"bucket": label, "n": 0, "detect_recall": 0.0, "exact_match": 0.0,
                    "char_accuracy": 0.0, "false_confident": 0.0, "mean_latency_ms": 0.0}
        return {
            "bucket": label,
            "n": n,
            "detect_recall": sum(1 for r in rs if r["detected"]) / n,
            "exact_match": sum(1 for r in rs if r["exact"]) / n,
            "char_accuracy": sum(r["char_acc"] for r in rs) / n,
            "false_confident": sum(
                1 for r in rs
                if r["confidence"] >= FALSE_CONFIDENT_THRESHOLD and not r["exact"]
            ) / n,
            "mean_latency_ms": sum(r["latency_ms"] for r in rs) / n,
        }

    rows = [summarise(b, [r for r in results if r["bucket"] == b]) for b in BUCKETS]
    rows.append(summarise("OVERALL", results))
    return rows


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def print_table(rows: List[Dict[str, Any]]) -> None:
    header = ("{:<16}{:>5}{:>9}{:>9}{:>10}{:>9}{:>10}"
              .format("bucket", "n", "detect", "exact", "char_acc", "false_c", "ms"))
    print(header)
    print("-" * len(header))
    for r in rows:
        if r["bucket"] == "OVERALL":
            print("-" * len(header))
        print("{:<16}{:>5}{:>8.1f}%{:>8.1f}%{:>9.1f}%{:>8.1f}%{:>10.1f}".format(
            r["bucket"], r["n"],
            r["detect_recall"] * 100, r["exact_match"] * 100,
            r["char_accuracy"] * 100, r["false_confident"] * 100,
            r["mean_latency_ms"],
        ))


def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "bucket": r["bucket"],
                "n": r["n"],
                "detect_recall": "{:.4f}".format(r["detect_recall"]),
                "exact_match": "{:.4f}".format(r["exact_match"]),
                "char_accuracy": "{:.4f}".format(r["char_accuracy"]),
                "false_confident": "{:.4f}".format(r["false_confident"]),
                "mean_latency_ms": "{:.2f}".format(r["mean_latency_ms"]),
            })


def write_per_image(path: str, results: List[Dict[str, Any]]) -> None:
    """Sidecar with one row per image - this is what you actually read to debug."""
    fields = ["bucket", "filename", "true_plate", "pred_plate", "status",
              "confidence", "detected", "exact", "char_acc", "latency_ms"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow({
                "bucket": r["bucket"],
                "filename": r["filename"],
                "true_plate": r["true_plate"],
                "pred_plate": r["pred_plate"],
                "status": r["status"],
                "confidence": "{:.4f}".format(r["confidence"]),
                "detected": int(r["detected"]),
                "exact": int(r["exact"]),
                "char_acc": "{:.4f}".format(r["char_acc"]),
                "latency_ms": "{:.2f}".format(r["latency_ms"]),
            })


def main() -> int:
    ap = argparse.ArgumentParser(description="IBVAP ANPR benchmark harness")
    ap.add_argument("--engine", choices=["current", "new"], required=True,
                    help="current = frozen pre-rebuild snapshot; new = live engine")
    ap.add_argument("--out", required=True, help="output CSV path for the summary table")
    ap.add_argument("--ground-truth", default=os.path.join(BENCH_DIR, "ground_truth.csv"))
    ap.add_argument("--per-image", default=None,
                    help="optional per-image CSV (default: <out> with .per_image.csv suffix)")
    args = ap.parse_args()

    rows = load_ground_truth(args.ground_truth)
    print("engine       : " + args.engine)
    print("ground truth : " + args.ground_truth + " (" + str(len(rows)) + " labelled rows)")

    if not rows:
        print("")
        print("no data - ground_truth.csv has no usable rows.")
        print("See tests/anpr_bench/README.md for the collection protocol (HUMAN GATE 1).")
        summary = aggregate([])
        print("")
        print_table(summary)
        write_csv(args.out, summary)
        print("")
        print("wrote " + args.out + " (zeros)")
        return 0

    engine = load_engine(args.engine)
    print("engine ready : " + str(getattr(engine, "is_ready", "unknown")))
    print("")

    results, missing = evaluate(engine, rows)

    if missing:
        print("  ! " + str(len(missing)) + " labelled image(s) not found on disk and excluded:")
        for m in missing[:10]:
            print("      " + m)
        if len(missing) > 10:
            print("      ... and " + str(len(missing) - 10) + " more")
        print("")

    summary = aggregate(results)
    print_table(summary)

    write_csv(args.out, summary)
    per_image = args.per_image or (os.path.splitext(args.out)[0] + ".per_image.csv")
    write_per_image(per_image, results)
    print("")
    print("wrote " + args.out)
    print("wrote " + per_image)
    if missing:
        print("WARNING: " + str(len(missing)) + " of " + str(len(rows))
              + " labelled images were missing; metrics cover "
              + str(len(results)) + " images.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
