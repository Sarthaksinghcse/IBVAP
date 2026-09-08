"""
IBVAP Night Vision — ANPR Regression Test
=========================================
Evaluates whether frame-level contrast enhancement introduces a double-CLAHE
regression on number plates (since ANPR applies its own plate-crop CLAHE).

Usage:
    python -m tests.night_vision.test_anpr_regression
    python -m tests.night_vision.test_anpr_regression --source storage/videos/clip.mp4 --simulate-night 0.25
"""
import os
import sys
import argparse
import logging
from typing import List, Dict, Any, Optional

import cv2
import numpy as np

# Ensure project root is in sys.path
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_here))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from ai_engine.intelligence.anpr_engine import get_anpr_engine
from ai_engine.night_vision import get_enhancer, NightVisionConfig, MODE_ALWAYS

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("anpr_regression")


def create_synthetic_vehicle_plate_image(plate_text: str = "DL01AB1234") -> np.ndarray:
    """Generate a realistic test image of a vehicle rear bumper with a number plate."""
    img = np.full((360, 640, 3), (80, 80, 80), dtype=np.uint8)

    # Vehicle body color & gradient
    cv2.rectangle(img, (100, 50), (540, 310), (40, 45, 55), -1)
    cv2.rectangle(img, (100, 50), (540, 310), (25, 25, 30), 3)

    # Plate background (White IND plate)
    px1, py1, px2, py2 = 220, 180, 420, 240
    cv2.rectangle(img, (px1, py1), (px2, py2), (245, 245, 245), -1)
    cv2.rectangle(img, (px1, py1), (px2, py2), (20, 20, 20), 2)

    # Blue IND strip on the left
    cv2.rectangle(img, (px1, py1), (px1 + 25, py2), (180, 50, 20), -1)

    # Plate text
    cv2.putText(
        img,
        plate_text,
        (px1 + 35, py1 + 42),
        cv2.FONT_HERSHEY_DUPLEX,
        1.0,
        (10, 10, 10),
        2,
        cv2.LINE_AA,
    )

    return img


def evaluate_anpr_on_frame(anpr_engine, frame: np.ndarray, vehicle_bbox: Dict[str, float]) -> Dict[str, Any]:
    """Run ANPR evaluation and return structured metrics."""
    res = anpr_engine.evaluate_vehicle_plate(
        frame_bgr=frame,
        vehicle_bbox=vehicle_bbox,
        camera_id="REGRESSION_TEST",
        track_id=1,
        vehicle_type="CAR",
    )
    return {
        "plate_detected": res.get("plate_detected", False),
        "plate_text": res.get("plate_text"),
        "plate_confidence": res.get("plate_confidence") or 0.0,
        "plate_status": res.get("plate_status", "NOT_DETECTED"),
    }


def run_anpr_regression_test(
    source: Optional[str] = None,
    simulate_night: float = 0.25,
    num_synthetic_samples: int = 10,
) -> Dict[str, Any]:
    """
    Compare ANPR performance across 4 conditions:
      1. Raw Daylight
      2. Enhanced Daylight
      3. Raw Low-Light (simulated night)
      4. Enhanced Low-Light (night vision applied)
    """
    logger.info("=" * 72)
    logger.info("IBVAP NIGHT VISION — ANPR REGRESSION SUITE (Double-CLAHE Check)")
    logger.info("=" * 72)

    anpr = get_anpr_engine()
    enhancer = get_enhancer(NightVisionConfig(mode=MODE_ALWAYS))

    # Test plate texts for synthetic generation
    test_plates = [
        "DL01AB1234", "MH12DE5678", "KA03MG9012", "HR26DK3456",
        "UP16BT7890", "WB02AE4321", "TN07CG8765", "GJ01XY2468",
        "CH01AB1111", "PB65TC9999",
    ][:num_synthetic_samples]

    results = {
        "day_raw": {"detected": 0, "readable": 0, "conf_sum": 0.0},
        "day_enhanced": {"detected": 0, "readable": 0, "conf_sum": 0.0},
        "night_raw": {"detected": 0, "readable": 0, "conf_sum": 0.0},
        "night_enhanced": {"detected": 0, "readable": 0, "conf_sum": 0.0},
    }

    frames_to_test = []
    if source and os.path.exists(source):
        cap = cv2.VideoCapture(source)
        count = 0
        while count < 30:
            ret, f = cap.read()
            if not ret:
                break
            frames_to_test.append((f, {"x": 10.0, "y": 10.0, "w": 80.0, "h": 80.0}, f"clip_frame_{count}"))
            count += 1
        cap.release()
    else:
        # Use synthetic vehicle samples
        for p in test_plates:
            img = create_synthetic_vehicle_plate_image(p)
            frames_to_test.append((img, {"x": 15.6, "y": 13.8, "w": 68.7, "h": 72.2}, p))

    total = len(frames_to_test)
    logger.info(f"Testing on {total} vehicle frame samples (simulate_night={simulate_night}) ...\n")

    for raw_day, bbox, label in frames_to_test:
        # 1. Day Raw
        r_day_raw = evaluate_anpr_on_frame(anpr, raw_day, bbox)
        if r_day_raw["plate_detected"]:
            results["day_raw"]["detected"] += 1
        if r_day_raw["plate_status"] == "READABLE":
            results["day_raw"]["readable"] += 1
            results["day_raw"]["conf_sum"] += r_day_raw["plate_confidence"]

        # 2. Day Enhanced
        enh_day = enhancer.enhance(raw_day)
        r_day_enh = evaluate_anpr_on_frame(anpr, enh_day, bbox)
        if r_day_enh["plate_detected"]:
            results["day_enhanced"]["detected"] += 1
        if r_day_enh["plate_status"] == "READABLE":
            results["day_enhanced"]["readable"] += 1
            results["day_enhanced"]["conf_sum"] += r_day_enh["plate_confidence"]

        # 3. Night Raw (dimmed + Gaussian sensor noise)
        dim = raw_day.astype(np.float32) * simulate_night
        noise = np.random.normal(0.0, 3.0, raw_day.shape).astype(np.float32)
        raw_night = np.clip(dim + noise, 0, 255).astype(np.uint8)

        r_night_raw = evaluate_anpr_on_frame(anpr, raw_night, bbox)
        if r_night_raw["plate_detected"]:
            results["night_raw"]["detected"] += 1
        if r_night_raw["plate_status"] == "READABLE":
            results["night_raw"]["readable"] += 1
            results["night_raw"]["conf_sum"] += r_night_raw["plate_confidence"]

        # 4. Night Enhanced
        enh_night = enhancer.enhance(raw_night)
        r_night_enh = evaluate_anpr_on_frame(anpr, enh_night, bbox)
        if r_night_enh["plate_detected"]:
            results["night_enhanced"]["detected"] += 1
        if r_night_enh["plate_status"] == "READABLE":
            results["night_enhanced"]["readable"] += 1
            results["night_enhanced"]["conf_sum"] += r_night_enh["plate_confidence"]

    # Format summary table
    logger.info(f"{'CONDITION':<24}{'PLATE DETECTED':>16}{'READABLE PLATES':>18}{'AVG CONFIDENCE':>14}")
    logger.info("-" * 72)
    for key, name in [
        ("day_raw", "Daylight Raw"),
        ("day_enhanced", "Daylight Enhanced"),
        ("night_raw", f"Night Raw (x{simulate_night})"),
        ("night_enhanced", "Night Enhanced (NV)"),
    ]:
        d = results[key]
        det_str = f"{d['detected']}/{total} ({d['detected']/total*100:.0f}%)"
        read_str = f"{d['readable']}/{total} ({d['readable']/total*100:.0f}%)"
        avg_c = (d["conf_sum"] / d["readable"]) if d["readable"] else 0.0
        logger.info(f"{name:<24}{det_str:>16}{read_str:>18}{avg_c:>13.1f}%")
    logger.info("=" * 72)

    # Regression verdict
    double_clahe_regression = False
    if results["night_enhanced"]["readable"] < results["night_raw"]["readable"]:
        double_clahe_regression = True
        logger.warning("\n[REGRESSION WARNING] Night Vision enhancement REDUCED readable plate reads.")
        logger.warning("Root cause: Double contrast-stretching (NightVision CLAHE + ANPR CLAHE).")
        logger.warning("Action: Feed raw frame crops to ANPR while YOLO receives enhanced frames.\n")
    else:
        logger.info("\nVERDICT: NO ANPR REGRESSION DETECTED. Night Vision maintains plate read integrity.\n")

    return {
        "results": results,
        "double_clahe_regression": double_clahe_regression,
    }


def main():
    parser = argparse.ArgumentParser(description="IBVAP ANPR Regression Test for Night Vision")
    parser.add_argument("--source", default=None, help="Optional video file with vehicles")
    parser.add_argument("--simulate-night", type=float, default=0.25, help="Simulated darkness gain (0.0-1.0)")
    args = parser.parse_args()

    run_anpr_regression_test(source=args.source, simulate_night=args.simulate_night)


if __name__ == "__main__":
    main()
