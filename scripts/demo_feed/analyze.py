"""
Stage 1 of the demo feed builder — run detection + tracking over a video once and
cache the per-frame tracks to disk.

Rendering is slow to iterate on and YOLO is the expensive part, so the two are
split: this writes a compact JSON of every track in every frame, and render.py
reads that back. Re-styling the overlay then costs seconds instead of minutes.

    python scripts/demo_feed/analyze.py --source storage/videos/normal_hall.mp4 \
        --out storage/demo_feed/normal_hall.tracks.json
"""
import os
import sys
import json
import time
import argparse

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import cv2
from ai_engine.detection.detector import Detector


def analyze(source: str, out_path: str, model_path: str, conf: float,
            max_frames: int = 0, stride: int = 1) -> dict:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise SystemExit(f"Could not open video: {source}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if max_frames:
        total = min(total, max_frames)

    detector = Detector(model_path=model_path, conf_threshold=conf)

    frames = []
    idx = 0
    started = time.time()

    while True:
        if max_frames and idx >= max_frames:
            break

        # Skipped frames are grabbed but never decoded, which is much cheaper
        # than a full read. Only used for the baseline pass, where the feature
        # statistics matter and every individual frame does not.
        if stride > 1 and idx % stride != 0:
            if not cap.grab():
                break
            idx += 1
            continue

        ok, frame = cap.read()
        if not ok or frame is None:
            break

        # Timestamp comes from the frame index, not the wall clock: the video is
        # processed slower than real time, so wall-clock deltas would make every
        # speed measurement wrong.
        t_video = idx / fps

        dets = detector.detect(frame, camera_id="DEMO", track=True)
        rows = []
        for d in dets:
            if d.track_id is None:
                continue
            rows.append({
                "id": int(d.track_id),
                "type": d.object_type,
                "conf": round(float(d.confidence), 1),
                # bbox is already normalised to percent (0-100) by Detector
                "x": round(float(d.bbox["x"]), 3),
                "y": round(float(d.bbox["y"]), 3),
                "w": round(float(d.bbox["w"]), 3),
                "h": round(float(d.bbox["h"]), 3),
            })

        frames.append({"i": idx, "t": round(t_video, 4), "tracks": rows})
        idx += 1

        if idx % 150 < stride:
            rate = idx / max(time.time() - started, 1e-6)
            eta = (total - idx) / max(rate, 1e-6)
            print(f"  [{idx}/{total}] {rate:.1f} fps, eta {eta/60:.1f} min", flush=True)

    cap.release()

    payload = {
        "source": os.path.relpath(source, _REPO_ROOT).replace("\\", "/"),
        "fps": fps,
        "width": width,
        "height": height,
        "frame_count": idx,
        "frames": frames,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    elapsed = time.time() - started
    n_tracks = len({r["id"] for f in frames for r in f["tracks"]})
    print(f"[analyze] {idx} frames, {n_tracks} distinct tracks, {elapsed/60:.1f} min -> {out_path}")
    return payload


def main():
    p = argparse.ArgumentParser(description="Cache detection+tracking output for the demo feed renderer.")
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--model", default=os.path.join(_REPO_ROOT, "models", "yolov8n.pt"))
    p.add_argument("--conf", type=float, default=0.35)
    p.add_argument("--max-frames", type=int, default=0, help="0 = whole video")
    p.add_argument("--stride", type=int, default=1, help="detect every Nth frame (baseline pass only)")
    a = p.parse_args()

    src = a.source if os.path.isabs(a.source) else os.path.join(_REPO_ROOT, a.source)
    out = a.out if os.path.isabs(a.out) else os.path.join(_REPO_ROOT, a.out)
    analyze(src, out, a.model, a.conf, a.max_frames, a.stride)


if __name__ == "__main__":
    main()
