"""
Stage 2 of the demo feed builder — turn cached tracks into an annotated MP4.

The baseline clip supplies the notion of "normal": the empirical distribution of
per-track motion features. The demo clip is then ranked against that
distribution, so an anomaly is literally "this does not look like the baseline"
rather than a hand-picked threshold.

Everything that makes the overlay look steady rather than twitchy lives here:
box smoothing, track hold-over, state hysteresis and minimum label dwell.

    python scripts/demo_feed/render.py \
        --baseline storage/demo_feed/normal_hall.tracks.json \
        --clip     storage/demo_feed/anomalous_hall.tracks.json \
        --video    storage/videos/anomalous_hall.mp4 \
        --out      storage/demo_feed/anomaly_demo_feed.mp4
"""
import os
import sys
import json
import math
import argparse
from collections import deque, defaultdict

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import cv2
import numpy as np

# ─── Motion analysis ──────────────────────────────────────────────────────────

WINDOW_FRAMES = 45      # ~1.5s of history at 30fps
MIN_MATURE    = 18      # frames before a track is worth judging

# ─── Overlay smoothing ────────────────────────────────────────────────────────

BOX_EMA          = 0.35   # lower = smoother, laggier boxes
HOLD_FRAMES      = 10     # keep drawing a track this long after it disappears
ENTER_SEV        = 0.50   # anomaly asserts above this severity...
EXIT_SEV         = 0.15   # ...and only clears below it (hysteresis)
ENTER_SUSTAIN    = 4      # consecutive frames above ENTER_SEV before asserting
EXIT_SUSTAIN     = 45     # ~1.5s hold, so an alert stays readable on screen
LABEL_MIN_FRAMES = 24     # a label stays put at least this long
EVENT_TTL_S      = 12.0   # how long a fired alert stays listed in the ticker

# ─── Palette (BGR) ────────────────────────────────────────────────────────────

C_NORMAL  = (140, 205, 150)
C_WATCH   = (70, 190, 245)
C_ANOMALY = (72, 74, 250)
C_INK     = (248, 248, 248)
C_PANEL   = (26, 24, 22)


CENTROID_EMA = 0.30   # smooths detector wobble out of the motion signal
MIN_STEP_PCT = 0.35   # steps smaller than this are noise, not movement


class Trajectory:
    """
    Rolling motion history for one track, in percent-of-frame coordinates.

    The centroid is low-pass filtered before anything is measured from it. Raw
    YOLO centroids wobble by a few tenths of a percent every frame even when the
    subject is still, and that wobble otherwise dominates both the reversal count
    and the tortuosity ratio — on the baseline clip it produced a median of 14
    "direction changes" per 45-frame window, none of which were real.
    """

    def __init__(self):
        self.pts = deque(maxlen=WINDOW_FRAMES)
        self.ts = deque(maxlen=WINDOW_FRAMES)
        self._s = None

    def add(self, cx, cy, t):
        if self._s is None:
            self._s = (cx, cy)
        else:
            self._s = (
                self._s[0] + CENTROID_EMA * (cx - self._s[0]),
                self._s[1] + CENTROID_EMA * (cy - self._s[1]),
            )
        self.pts.append(self._s)
        self.ts.append(t)

    @property
    def mature(self):
        return len(self.pts) >= MIN_MATURE

    def speed(self):
        """Percent of frame traversed per second, averaged over the window."""
        if len(self.pts) < 2:
            return 0.0
        dt = self.ts[-1] - self.ts[0]
        if dt <= 0:
            return 0.0
        path = sum(
            math.dist(self.pts[i], self.pts[i + 1])
            for i in range(len(self.pts) - 1)
        )
        return path / dt

    def tortuosity(self):
        """Path length over straight-line displacement. 1.0 is a straight line."""
        if len(self.pts) < 2:
            return 1.0
        path = sum(
            math.dist(self.pts[i], self.pts[i + 1])
            for i in range(len(self.pts) - 1)
        )
        disp = math.dist(self.pts[0], self.pts[-1])
        if disp < 0.5:          # essentially returned to where it started
            return min(path / 0.5, 40.0) if path > 0 else 1.0
        return min(path / disp, 40.0)

    def reversals(self):
        """Count of sharp direction changes across the window."""
        if len(self.pts) < 3:
            return 0
        n = 0
        for i in range(1, len(self.pts) - 1):
            ax = self.pts[i][0] - self.pts[i - 1][0]
            ay = self.pts[i][1] - self.pts[i - 1][1]
            bx = self.pts[i + 1][0] - self.pts[i][0]
            by = self.pts[i + 1][1] - self.pts[i][1]
            na, nb = math.hypot(ax, ay), math.hypot(bx, by)
            # Ignore steps too small to be real movement, otherwise a stationary
            # subject registers a reversal on almost every frame.
            if na < MIN_STEP_PCT or nb < MIN_STEP_PCT:
                continue
            cos_t = max(-1.0, min(1.0, (ax * bx + ay * by) / (na * nb)))
            if math.degrees(math.acos(cos_t)) > 95.0:
                n += 1
        return n

    def features(self):
        return (self.speed(), self.tortuosity(), float(self.reversals()))


def collect_features(cache):
    """Every mature track-frame in a cache, as (speed, tortuosity, reversals) rows."""
    trajs = defaultdict(Trajectory)
    rows = []
    for fr in cache["frames"]:
        seen = set()
        for tr in fr["tracks"]:
            if tr["type"] != "PERSON":
                continue
            seen.add(tr["id"])
            traj = trajs[tr["id"]]
            traj.add(tr["x"] + tr["w"] / 2.0, tr["y"] + tr["h"] / 2.0, fr["t"])
            if traj.mature:
                rows.append(traj.features())
        for gone in [k for k in trajs if k not in seen]:
            pass  # keep history; tracks reappear after brief occlusion
    return np.array(rows, dtype=np.float32) if rows else np.zeros((0, 3), np.float32)


class Baseline:
    """
    What "normal" looks like, kept as the raw sorted feature distributions.

    The baseline is strongly right-skewed (speed median 2.4 %/s but 95th
    percentile 21 %/s), so a mean/sigma model badly misjudges it — one standard
    deviation lands inside the bulk and everything in the tail scores as a wild
    outlier. Comparing by percentile rank instead is both better behaved and
    easier to justify out loud: "faster than 99% of normal movement".
    """

    # Only speed and tortuosity are scored. The reversal count survives as a
    # diagnostic but makes a terrible ranking feature: after centroid smoothing
    # its baseline p99 is 1, so an integer count of 2 saturates the percentile
    # and every track that wobbles twice reads as a maximal anomaly.
    FEATURES = (("speed", 0), ("tortuosity", 1))

    def __init__(self, rows):
        self.cols = [np.sort(rows[:, i]) for i in range(rows.shape[1])]
        self.p50 = np.percentile(rows, 50, axis=0)
        self.p99 = np.percentile(rows, 99, axis=0)
        # Distance from typical to extreme, used to grade how far past p99 a
        # value sits. Without it severity is binary and every flagged track
        # looks equally severe.
        self.spread = np.maximum(self.p99 - self.p50, 1e-3)

    def pct_rank(self, i, value):
        """Percentile of `value` within baseline feature `i`, as 0-100."""
        col = self.cols[i]
        return 100.0 * float(np.searchsorted(col, value, side="right")) / len(col)

    def describe(self):
        names = ["speed %/s", "tortuosity", "reversals"]
        for i, n in enumerate(names):
            scored = " (scored)" if i in (0, 1) else " (diagnostic only)"
            print(f"[render]   {n:11s} p50 {self.p50[i]:6.2f}  p99 {self.p99[i]:6.2f}{scored}")


def score(feats, base: Baseline):
    """
    Returns (severity, driver_label, percentile_rank).

    Severity counts how far past the baseline's 99th percentile a value sits,
    measured in units of (p99 - p50). It stays graded instead of saturating, so
    a sprint outranks a brisk walk instead of both pinning at maximum.
    """
    values = (feats[0], feats[1])
    labels = ("RUNNING", "ERRATIC PATH")

    best_sev, best_label, best_rank = 0.0, "NORMAL", 0.0
    for idx, (v, label) in enumerate(zip(values, labels)):
        sev = max(0.0, (v - base.p99[idx]) / base.spread[idx])
        if sev > best_sev:
            best_sev = sev
            best_label = label
            best_rank = base.pct_rank(idx, v)
    return best_sev, best_label, best_rank


# ─── Drawing ──────────────────────────────────────────────────────────────────

def corner_box(img, x1, y1, x2, y2, color, thick=2, frac=0.22):
    """Corner brackets rather than a full rectangle — less visual noise on busy frames."""
    w, h = x2 - x1, y2 - y1
    ln = max(10, int(min(w, h) * frac))
    for px, py, dx, dy in (
        (x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)
    ):
        cv2.line(img, (px, py), (px + dx * ln, py), color, thick, cv2.LINE_AA)
        cv2.line(img, (px, py), (px, py + dy * ln), color, thick, cv2.LINE_AA)


def chip(img, x, y, text, color, scale=0.46, pad=6):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    y = max(y, th + pad * 2 + 2)
    tl = (x, y - th - pad * 2)
    br = (x + tw + pad * 2, y)
    panel = img[max(tl[1], 0):br[1], max(tl[0], 0):br[0]]
    if panel.size:
        panel[:] = cv2.addWeighted(panel, 0.25, np.full_like(panel, color), 0.75, 0)
    cv2.putText(img, text, (x + pad, y - pad), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (18, 18, 18), 1, cv2.LINE_AA)
    return br[1]


def translucent(img, x1, y1, x2, y2, color, alpha):
    roi = img[y1:y2, x1:x2]
    if roi.size:
        roi[:] = cv2.addWeighted(roi, 1 - alpha, np.full_like(roi, color), alpha, 0)


def header(img, cam_name, t_video, n_tracks, n_anom):
    W = img.shape[1]
    translucent(img, 0, 0, W, 54, C_PANEL, 0.72)
    cv2.circle(img, (26, 27), 6, (80, 80, 245) if n_anom else (120, 220, 130), -1, cv2.LINE_AA)
    cv2.putText(img, cam_name, (44, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.62, C_INK, 1, cv2.LINE_AA)

    mm, ss = divmod(int(t_video), 60)
    stamp = f"{mm:02d}:{ss:02d}"
    right = [
        (stamp, C_INK),
        (f"TRACKS {n_tracks}", C_INK),
        (f"ANOMALIES {n_anom}", C_ANOMALY if n_anom else (150, 150, 150)),
    ]
    x = W - 20
    for text, col in reversed(right):
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        x -= tw
        cv2.putText(img, text, (x, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
        x -= 26


def ticker(img, lines):
    if not lines:
        return
    H, W = img.shape[:2]
    h = 26 * len(lines) + 16
    translucent(img, 0, H - h, W, H, C_PANEL, 0.72)
    y = H - h + 24
    for text, col in lines:
        cv2.circle(img, (22, y - 5), 4, col, -1, cv2.LINE_AA)
        cv2.putText(img, text, (38, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, C_INK, 1, cv2.LINE_AA)
        y += 26


# ─── Main render ──────────────────────────────────────────────────────────────

class TrackView:
    """Per-track render state: smoothed geometry plus debounced anomaly status."""

    def __init__(self):
        self.traj = Trajectory()
        self.box = None          # smoothed (x, y, w, h) in percent
        self.missing = 0
        self.above = 0
        self.below = 0
        self.anomalous = False
        self.label = "NORMAL"
        self.label_age = 0
        self.z = 0.0
        self.rank = 0.0
        self.ratio = 0.0


def render(baseline_path, clip_path, video_path, out_path, cam_name, width_out, max_seconds):
    with open(baseline_path, encoding="utf-8") as fh:
        baseline = json.load(fh)
    with open(clip_path, encoding="utf-8") as fh:
        clip = json.load(fh)

    base_rows = collect_features(baseline)
    if len(base_rows) < 50:
        raise SystemExit(f"Baseline has too few mature samples ({len(base_rows)}) to model normal.")
    base = Baseline(base_rows)
    print(f"[render] baseline: {len(base_rows)} mature samples from {baseline['source']}")
    base.describe()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise SystemExit(f"Could not open video: {video_path}")
    fps = clip.get("fps") or cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    W = width_out
    H = int(round(src_h * (W / src_w) / 2) * 2)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    if not writer.isOpened():
        raise SystemExit("Could not open VideoWriter")

    by_index = {f["i"]: f for f in clip["frames"]}
    views = defaultdict(TrackView)
    events = deque(maxlen=3)
    total_anom_tracks = set()
    written = 0
    limit = int(max_seconds * fps) if max_seconds else 0

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if limit and written >= limit:
            break

        idx = written
        frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)
        fr = by_index.get(idx)
        t_video = idx / fps

        present = set()
        if fr:
            for tr in fr["tracks"]:
                if tr["type"] != "PERSON":
                    continue
                tid = tr["id"]
                present.add(tid)
                v = views[tid]
                v.missing = 0

                raw = (tr["x"], tr["y"], tr["w"], tr["h"])
                v.box = raw if v.box is None else tuple(
                    v.box[i] + BOX_EMA * (raw[i] - v.box[i]) for i in range(4)
                )
                v.traj.add(tr["x"] + tr["w"] / 2.0, tr["y"] + tr["h"] / 2.0, t_video)

                if v.traj.mature:
                    sev, driver, rank = score(v.traj.features(), base)
                    _f = v.traj.features()
                    _i = 0 if driver == "RUNNING" else 1
                    v.ratio = _f[_i] / max(base.p99[_i], 1e-6)
                    v.z = v.z + 0.25 * (sev - v.z)      # smooth the severity itself
                    v.rank = rank

                    if v.z >= ENTER_SEV:
                        v.above += 1
                        v.below = 0
                    elif v.z <= EXIT_SEV:
                        v.below += 1
                        v.above = 0

                    if not v.anomalous and v.above >= ENTER_SUSTAIN:
                        v.anomalous = True
                        v.label = driver
                        v.label_age = 0
                        total_anom_tracks.add(tid)
                        feats = v.traj.features()
                        obs, ref = (feats[0], base.p99[0]) if driver == "RUNNING"                             else (feats[1], base.p99[1])
                        unit = "%/s" if driver == "RUNNING" else ""
                        events.appendleft((
                            f"{int(t_video)//60:02d}:{int(t_video)%60:02d}  "
                            f"Track #{tid} - {driver.title()}  "
                            f"{obs:.0f}{unit} vs baseline 99th pct {ref:.0f}{unit}",
                            C_ANOMALY,
                            t_video,
                        ))
                    elif v.anomalous and v.below >= EXIT_SUSTAIN:
                        v.anomalous = False
                        v.label = "NORMAL"
                        v.label_age = 0

                    v.label_age += 1
                    if v.anomalous and v.label_age > LABEL_MIN_FRAMES and driver != v.label:
                        v.label = driver
                        v.label_age = 0

        for tid, v in list(views.items()):
            if tid not in present:
                v.missing += 1
                if v.missing > HOLD_FRAMES:
                    del views[tid]

        n_anom = 0
        for tid, v in views.items():
            if v.box is None:
                continue
            x, y, w, h = v.box
            x1, y1 = int(x / 100 * W), int(y / 100 * H)
            x2, y2 = int((x + w) / 100 * W), int((y + h) / 100 * H)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(W - 1, x2), min(H - 1, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            if v.anomalous:
                col = C_ANOMALY
                n_anom += 1
            elif v.traj.mature and v.z >= EXIT_SEV:
                col = C_WATCH
            else:
                col = C_NORMAL

            corner_box(frame, x1, y1, x2, y2, col, 2 if not v.anomalous else 3)
            tag = f"ID {tid}"
            if v.anomalous:
                tag += f"  {v.label}  {v.ratio:.1f}x"
            chip(frame, x1, y1 - 4, tag, col)

        header(frame, cam_name, t_video, len(views), n_anom)
        live_events = [(txt, col) for txt, col, born in events
                       if t_video - born <= EVENT_TTL_S]
        ticker(frame, live_events)

        writer.write(frame)
        written += 1
        if written % 300 == 0:
            print(f"  rendered {written} frames", flush=True)

    cap.release()
    writer.release()
    size_mb = os.path.getsize(out_path) / 1e6
    print(f"[render] {written} frames -> {out_path} ({size_mb:.1f} MB)")
    print(f"[render] {len(total_anom_tracks)} distinct tracks flagged anomalous")


def main():
    p = argparse.ArgumentParser(description="Render an annotated demo feed from cached tracks.")
    p.add_argument("--baseline", required=True)
    p.add_argument("--clip", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--name", default="CAM-DEMO  ·  HALL PERIMETER")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--max-seconds", type=float, default=0)
    a = p.parse_args()

    def abspath(v):
        return v if os.path.isabs(v) else os.path.join(_REPO_ROOT, v)

    render(abspath(a.baseline), abspath(a.clip), abspath(a.video),
           abspath(a.out), a.name, a.width, a.max_seconds)


if __name__ == "__main__":
    main()
