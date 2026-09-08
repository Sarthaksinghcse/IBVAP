"""
IBVAP Night Vision — A/B Detection Benchmark
============================================
Answers the only question that matters for this layer:

    Does enhancement improve reliable detection in night conditions?

The implementation plan is explicit that enhancement must NOT be judged by how
bright the output looks. So this harness runs the *same* YOLOv8 model over the
*same* frames twice — once raw, once enhanced — and compares detection outcomes.

Usage
-----
    python -m ai_engine.night_vision.benchmark --source storage/videos/clip.mp4

    # Simulate night on daylight footage (no night clip on hand yet):
    python -m ai_engine.night_vision.benchmark --source clip.mp4 --simulate-night 0.2

    # Write side-by-side comparison frames for the report/demo:
    python -m ai_engine.night_vision.benchmark --source clip.mp4 --save-samples out/

Reported metrics
----------------
    detections           total objects detected across sampled frames
    frames_with_objects  recall proxy — a frame YOLO found nothing in is a
                         potential missed intrusion, the failure mode that
                         matters most for border security
    mean_confidence      average detection confidence (0-100)
    per-class counts     PERSON / VEHICLE / ANIMAL breakdown
    fps                  end-to-end throughput including enhancement cost

Without ground-truth annotations this measures *detection yield*, not mAP.
Yield is the honest, self-contained signal available from unlabelled footage;
mAP requires the annotated dataset from Phase 4 of the plan.
"""
import os
import sys
import time
import json
import argparse
import logging
from typing import Optional, Dict, Any, List

import cv2
import numpy as np

# Allow `python ai_engine/night_vision/benchmark.py` as well as `-m`
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_here))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from ai_engine.detection.detector import Detector
from ai_engine.night_vision.config import NightVisionConfig, MODE_ALWAYS, MODE_OFF
from ai_engine.night_vision.enhancement import NightVisionEnhancer

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("nv_benchmark")


class RunMetrics:
    """Accumulated detection metrics for one pass over the footage."""

    def __init__(self, label: str):
        self.label = label
        self.frames = 0
        self.frames_with_objects = 0
        self.detections = 0
        self.confidence_sum = 0.0
        self.per_class: Dict[str, int] = {}
        self.elapsed_sec = 0.0
        self.enhance_ms_total = 0.0
        self.per_frame_counts: List[int] = []

    def record(self, detections, enhance_ms: float = 0.0) -> None:
        self.frames += 1
        self.enhance_ms_total += enhance_ms
        n = len(detections)
        self.per_frame_counts.append(n)
        if n:
            self.frames_with_objects += 1
        self.detections += n
        for d in detections:
            self.confidence_sum += d.confidence
            self.per_class[d.object_type] = self.per_class.get(d.object_type, 0) + 1

    @property
    def mean_confidence(self) -> float:
        return self.confidence_sum / self.detections if self.detections else 0.0

    @property
    def detection_rate(self) -> float:
        """Fraction of frames in which the detector found at least one object."""
        return self.frames_with_objects / self.frames if self.frames else 0.0

    @property
    def fps(self) -> float:
        return self.frames / self.elapsed_sec if self.elapsed_sec > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "frames": self.frames,
            "detections": self.detections,
            "frames_with_objects": self.frames_with_objects,
            "detection_rate": round(self.detection_rate, 4),
            "mean_confidence": round(self.mean_confidence, 2),
            "per_class": dict(sorted(self.per_class.items())),
            "fps": round(self.fps, 2),
            "elapsed_sec": round(self.elapsed_sec, 2),
            "avg_enhance_ms": round(self.enhance_ms_total / self.frames, 2) if self.frames else 0.0,
        }


def _dim_frame(frame: np.ndarray, factor: float) -> np.ndarray:
    """
    Simulate a night capture from daylight footage.

    Applies a multiplicative gain drop plus Gaussian sensor noise. Real low-light
    sensor behaviour is more complex (read noise, photon shot noise, ISO gain),
    so treat simulated results as directional evidence, not a substitute for
    measuring on genuine night footage.
    """
    dim = frame.astype(np.float32) * factor
    noise = np.random.normal(0.0, 4.0, frame.shape).astype(np.float32)
    return np.clip(dim + noise, 0, 255).astype(np.uint8)


def _run_pass(
    label: str,
    source: str,
    detector: Detector,
    enhancer: Optional[NightVisionEnhancer],
    max_frames: int,
    sample_step: int,
    simulate_night: Optional[float],
    seed: int,
    save_dir: Optional[str],
) -> RunMetrics:
    """Run one full pass over the footage, with or without enhancement."""
    metrics = RunMetrics(label)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    # Identical noise realisation in both passes, so the two runs differ only by
    # enhancement rather than by the random night simulation.
    np.random.seed(seed)

    frame_idx = 0
    started = time.perf_counter()
    try:
        while metrics.frames < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            current = frame_idx
            frame_idx += 1
            if (current % sample_step) != 0:
                continue

            if simulate_night is not None:
                frame = _dim_frame(frame, simulate_night)

            enhance_ms = 0.0
            infer_frame = frame
            if enhancer is not None:
                result = enhancer.process(frame)
                infer_frame = result.frame
                enhance_ms = result.elapsed_ms

            # track=False: tracker state would carry across the two passes and
            # confound the comparison. Pure per-frame detection is what we want.
            detections = detector.detect(infer_frame, camera_id="BENCH", track=False)
            metrics.record(detections, enhance_ms)

            if save_dir and metrics.frames <= 5:
                os.makedirs(save_dir, exist_ok=True)
                name = f"{metrics.frames:02d}_{label.lower().replace(' ', '_')}.jpg"
                annotated = infer_frame.copy()
                h, w = annotated.shape[:2]
                for d in detections:
                    x = int(d.bbox["x"] / 100.0 * w)
                    y = int(d.bbox["y"] / 100.0 * h)
                    bw = int(d.bbox["w"] / 100.0 * w)
                    bh = int(d.bbox["h"] / 100.0 * h)
                    cv2.rectangle(annotated, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
                    cv2.putText(annotated, f"{d.object_type} {d.confidence:.0f}%",
                                (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                                0.5, (0, 255, 0), 1)
                cv2.putText(annotated, f"{label}: {len(detections)} objects",
                            (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)
                cv2.imwrite(os.path.join(save_dir, name), annotated)
    finally:
        cap.release()
        metrics.elapsed_sec = time.perf_counter() - started

    return metrics


def _warmup(detector: Detector, source: str, frames: int = 3) -> None:
    """
    Run a few throwaway inferences (and one throwaway enhancement) so neither
    timed pass absorbs lazy-initialisation cost.
    """
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return
    warm_enhancer = NightVisionEnhancer(NightVisionConfig(mode=MODE_ALWAYS))
    try:
        for _ in range(frames):
            ret, frame = cap.read()
            if not ret:
                break
            detector.detect(frame, camera_id="WARMUP", track=False)
            detector.detect(warm_enhancer.enhance(frame), camera_id="WARMUP", track=False)
    finally:
        cap.release()


def _pct_delta(baseline: float, candidate: float) -> str:
    """Format a relative change, guarding the zero-baseline case."""
    if baseline == 0:
        return "n/a (baseline 0)" if candidate == 0 else f"+{candidate:.2f} from 0"
    return f"{(candidate - baseline) / baseline * 100.0:+.1f}%"


def run_benchmark(
    source: str,
    model_path: str,
    conf: float = 0.35,
    max_frames: int = 200,
    sample_step: int = 5,
    simulate_night: Optional[float] = None,
    seed: int = 1234,
    save_dir: Optional[str] = None,
    config: Optional[NightVisionConfig] = None,
) -> Dict[str, Any]:
    """Run the raw-vs-enhanced A/B comparison and return a metrics report."""
    detector = Detector(model_path=model_path, conf_threshold=conf)

    cfg = config or NightVisionConfig()
    # ALWAYS, so the enhanced pass is genuinely enhanced even if the classifier
    # would have called this footage well-lit. The A/B must not be a no-op.
    cfg.mode = MODE_ALWAYS
    cfg.validate()

    logger.info("=" * 74)
    logger.info("IBVAP NIGHT VISION — A/B DETECTION BENCHMARK")
    logger.info("=" * 74)
    logger.info(f"  Source          : {source}")
    logger.info(f"  Model           : {model_path}")
    logger.info(f"  Confidence      : {conf}")
    logger.info(f"  Frames sampled  : up to {max_frames} (every {sample_step}th frame)")
    if simulate_night is not None:
        logger.info(f"  Night simulation: gain x{simulate_night} + Gaussian noise")
    logger.info("=" * 74)

    # Warm up the model before either timed pass. YOLO's first inference pays
    # lazy CUDA/kernel initialisation; charging that to whichever pass runs
    # first makes the FPS comparison meaningless.
    _warmup(detector, source)

    logger.info("\n[1/2] Baseline pass — raw frames, no enhancement ...")
    baseline = _run_pass("BASELINE", source, detector, None, max_frames,
                         sample_step, simulate_night, seed, save_dir)

    logger.info("[2/2] Enhanced pass — night vision enabled ...")
    enhanced = _run_pass("ENHANCED", source, detector, NightVisionEnhancer(cfg),
                         max_frames, sample_step, simulate_night, seed, save_dir)

    b, e = baseline.to_dict(), enhanced.to_dict()

    logger.info("\n" + "=" * 74)
    logger.info(f"{'METRIC':<26}{'BASELINE':>15}{'ENHANCED':>15}{'CHANGE':>18}")
    logger.info("-" * 74)
    rows = [
        ("Frames analysed",      b["frames"],              e["frames"],              ""),
        ("Total detections",     b["detections"],          e["detections"],
         _pct_delta(b["detections"], e["detections"])),
        ("Frames with objects",  b["frames_with_objects"], e["frames_with_objects"],
         _pct_delta(b["frames_with_objects"], e["frames_with_objects"])),
        ("Detection rate",       f"{b['detection_rate']:.1%}", f"{e['detection_rate']:.1%}",
         f"{(e['detection_rate'] - b['detection_rate']) * 100:+.1f} pp"),
        ("Mean confidence",      f"{b['mean_confidence']:.1f}%", f"{e['mean_confidence']:.1f}%",
         _pct_delta(b["mean_confidence"], e["mean_confidence"])),
        ("Throughput (FPS)",     f"{b['fps']:.1f}",        f"{e['fps']:.1f}",
         _pct_delta(b["fps"], e["fps"])),
        ("Avg enhance cost",     "0.00 ms",                f"{e['avg_enhance_ms']:.2f} ms", ""),
    ]
    for name, bv, ev, delta in rows:
        logger.info(f"{name:<26}{str(bv):>15}{str(ev):>15}{delta:>18}")

    logger.info("-" * 74)
    all_classes = sorted(set(b["per_class"]) | set(e["per_class"]))
    for cls in all_classes:
        bc, ec = b["per_class"].get(cls, 0), e["per_class"].get(cls, 0)
        logger.info(f"{'  class ' + cls:<26}{bc:>15}{ec:>15}{_pct_delta(bc, ec):>18}")
    logger.info("=" * 74)

    verdict = _verdict(b, e)
    logger.info(f"\nVERDICT: {verdict}\n")

    report = {
        "source": source,
        "model": model_path,
        "conf_threshold": conf,
        "simulate_night": simulate_night,
        "night_vision_config": cfg.to_dict(),
        "baseline": b,
        "enhanced": e,
        "verdict": verdict,
    }
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        report_path = os.path.join(save_dir, "benchmark_report.json")
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        logger.info(f"Report written to {report_path}")
        logger.info(f"Comparison frames written to {save_dir}")

    return report


def _verdict(b: Dict[str, Any], e: Dict[str, Any]) -> str:
    """State plainly whether enhancement helped, hurt, or did nothing measurable."""
    det_delta = e["detections"] - b["detections"]
    rate_delta = e["detection_rate"] - b["detection_rate"]
    conf_delta = e["mean_confidence"] - b["mean_confidence"]

    if b["detections"] == 0 and e["detections"] == 0:
        return ("Neither pass detected anything. The footage is too dark, too small, or "
                "contains no supported classes — enhancement cannot be judged from this clip.")

    gains = []
    losses = []
    for name, delta, unit in (
        ("total detections", det_delta, ""),
        ("detection rate", rate_delta * 100, " pp"),
        ("mean confidence", conf_delta, " pts"),
    ):
        if delta > 0:
            gains.append(f"{name} {delta:+.1f}{unit}")
        elif delta < 0:
            losses.append(f"{name} {delta:+.1f}{unit}")

    if gains and not losses:
        return "Enhancement IMPROVED detection — " + ", ".join(gains) + "."
    if losses and not gains:
        return "Enhancement DEGRADED detection — " + ", ".join(losses) + ". Do not enable for this footage."
    if gains and losses:
        return ("Enhancement had MIXED effect — gained " + ", ".join(gains) +
                "; lost " + ", ".join(losses) + ". Tune thresholds before enabling.")
    return "Enhancement made NO measurable difference on this footage."


def main():
    default_model = os.path.join(_project_root, "models", "yolov8n.pt")

    parser = argparse.ArgumentParser(description="IBVAP Night Vision A/B detection benchmark")
    parser.add_argument("--source", required=True, help="Path to video file or stream URL")
    parser.add_argument("--model", default=default_model, help="Path to YOLOv8 weights")
    parser.add_argument("--conf", type=float, default=0.35, help="Detection confidence threshold")
    parser.add_argument("--max-frames", type=int, default=200, help="Max frames to analyse per pass")
    parser.add_argument("--sample-step", type=int, default=5, help="Analyse every Nth frame")
    parser.add_argument("--simulate-night", type=float, default=None, metavar="GAIN",
                        help="Simulate night on daylight footage (e.g. 0.2 = 20%% brightness)")
    parser.add_argument("--seed", type=int, default=1234, help="RNG seed for night simulation")
    parser.add_argument("--save-samples", default=None, metavar="DIR",
                        help="Write annotated comparison frames and a JSON report here")
    args = parser.parse_args()

    if args.simulate_night is not None and not (0.0 < args.simulate_night <= 1.0):
        parser.error("--simulate-night must be in (0.0, 1.0]")

    run_benchmark(
        source=args.source,
        model_path=args.model,
        conf=args.conf,
        max_frames=args.max_frames,
        sample_step=args.sample_step,
        simulate_night=args.simulate_night,
        seed=args.seed,
        save_dir=args.save_samples,
    )


if __name__ == "__main__":
    main()
