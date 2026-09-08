"""
IBVAP — Video Number Plate Detection (ANPR) Test Suite
======================================================
Tests the ANPR and YOLOv8 pipeline on real video frames to evaluate:
1. Detection of vehicle tracks from video footage.
2. Number plate localization and extraction on vehicle crops.
3. Accurate rejection and handling when NO PLATE is detected (plate_status='NOT_DETECTED').
4. Real-time OCR evaluation on readable vs unreadable vs absent plate surfaces.
"""
import os
import sys
import cv2
import numpy as np

# Set project roots
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO_ROOT)

from ai_engine.detection.detector import Detector
from ai_engine.tracking.tracker import Tracker
from ai_engine.intelligence.anpr_engine import get_anpr_engine


def test_plate_detection_on_video(video_path: Optional[str] = None):
    print("=" * 75)
    print("      IBVAP: TESTING NUMBER PLATE (ANPR) DETECTION ON VIDEO")
    print("=" * 75)

    if video_path is None:
        video_path = os.path.join(REPO_ROOT, "storage", "videos", "test_border.mp4")

    if not os.path.exists(video_path):
        print(f"[ERROR] Video file not found: {video_path}")
        return

    # Initialize YOLO Detector & ANPR Engine
    print(f"\n[1] Initializing YOLOv8n Detector and CRNN ANPR Engine...")
    detector = Detector(conf_threshold=0.35)
    tracker = Tracker()
    anpr_engine = get_anpr_engine()

    assert anpr_engine.is_ready, "ANPR Engine CRNN model not loaded!"
    print("  -> YOLOv8n and CRNN OCR models successfully initialized.")

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"\n[2] Processing Video: {os.path.basename(video_path)}")
    print(f"    Dimensions: {width}x{height} | FPS: {fps:.1f} | Total Frames: {total_frames}")

    frame_idx = 0
    sampled_count = 0
    vehicles_evaluated = 0
    no_plate_count = 0
    plate_detected_count = 0
    results_summary = []

    # Process all video frames (sampled at step=6) to inspect vehicle detections
    sample_step = 6
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        current_idx = frame_idx
        frame_idx += 1

        if current_idx % sample_step != 0:
            continue

        sampled_count += 1
        video_time = current_idx / fps

        # 1. Run YOLOv8 detection
        detections = detector.detect(frame, camera_id="BOP-07", track=True)
        active_tracks = tracker.update(detections)

        # Filter vehicle tracks
        vehicle_tracks = [t for t in active_tracks if t.object_type == "VEHICLE"]

        for vtrack in vehicle_tracks:
            vehicles_evaluated += 1
            # Evaluate ANPR on this vehicle
            v_type = vtrack.object_label.split(" ")[0].upper() if " " in vtrack.object_label else "CAR"
            plate_res = anpr_engine.evaluate_vehicle_plate(
                frame_bgr=frame,
                vehicle_bbox=vtrack.bbox,
                camera_id="BOP-07",
                track_id=vtrack.track_id,
                vehicle_type=v_type,
                force_refresh=True
            )

            is_plate_found = plate_res.get("plate_detected", False)
            plate_status = plate_res.get("plate_status", "NOT_DETECTED")
            plate_text = plate_res.get("plate_text")
            plate_conf = plate_res.get("plate_confidence")

            if is_plate_found and plate_text:
                plate_detected_count += 1
            else:
                no_plate_count += 1

            results_summary.append({
                "frame": current_idx,
                "time_sec": round(video_time, 2),
                "track_id": vtrack.track_id,
                "label": vtrack.object_label,
                "bbox": vtrack.bbox,
                "plate_detected": is_plate_found,
                "plate_status": plate_status,
                "plate_text": plate_text,
                "confidence": plate_conf
            })

    cap.release()

    print(f"\n[3] Video Analysis Summary:")
    print(f"    - Frames Sampled: {sampled_count}")
    print(f"    - Vehicle Instances Evaluated: {vehicles_evaluated}")
    print(f"    - 'NO PLATE' Detections (plate_status = 'NOT_DETECTED'): {no_plate_count}")
    print(f"    - 'PLATE DETECTED' Instances: {plate_detected_count}")

    print("\n[4] Sample Results Breakdown from Video:")
    if results_summary:
        print(f"    {'Timestamp':<10} | {'Object Label':<16} | {'Plate Detected':<15} | {'Plate Status':<14} | {'Plate Text':<12}")
        print("    " + "-" * 75)
        for r in results_summary[:12]:
            det_str = "YES" if r["plate_detected"] else "NO"
            text_str = r["plate_text"] if r["plate_text"] else "—"
            print(f"    T+{r['time_sec']:<6.1f}s  | {r['label']:<16} | {det_str:<15} | {r['plate_status']:<14} | {text_str:<12}")
    else:
        print("    (No vehicles appeared in the initial sampled interval of the test video)")

    # [5] Test No-Plate vs With-Plate verification on injected video frames
    print("\n[5] Controlled Verification: Vehicle WITH Plate vs Vehicle WITHOUT Plate:")
    
    from backend.test_anpr import _create_synthetic_vehicle_with_plate

    # Test Vehicle #1: Car WITHOUT license plate (Smooth bumper)
    frame_no_plate = np.zeros((400, 600, 3), dtype=np.uint8)
    no_plate_crop = _create_synthetic_vehicle_with_plate(no_plate=True)
    frame_no_plate[120:320, 120:420] = cv2.resize(no_plate_crop, (300, 200))
    v_bbox = {"x": 20.0, "y": 30.0, "w": 50.0, "h": 50.0}

    eval_no_plate = anpr_engine.evaluate_vehicle_plate(
        frame_bgr=frame_no_plate,
        vehicle_bbox=v_bbox,
        camera_id="BOP-07",
        track_id=101,
        vehicle_type="CAR",
        force_refresh=True
    )
    print(f"    * Test Vehicle #1 (NO PLATE):")
    print(f"      - plate_detected: {eval_no_plate['plate_detected']}")
    print(f"      - plate_status:   '{eval_no_plate['plate_status']}'")
    print(f"      - plate_text:     {eval_no_plate['plate_text']}")
    assert eval_no_plate["plate_text"] is None or eval_no_plate["plate_status"] in ["NOT_DETECTED", "UNREADABLE"]
    print("      -> [PASS] Correctly rejected non-plate vehicle surface as UNREADABLE/NOT_DETECTED with zero fake text.")

    # Test Vehicle #2: Car WITH clear license plate "DL01AB1234"
    frame_with_plate = np.zeros((400, 600, 3), dtype=np.uint8)
    with_plate_crop = _create_synthetic_vehicle_with_plate("DL01AB1234")
    frame_with_plate[120:320, 120:420] = cv2.resize(with_plate_crop, (300, 200))

    eval_with_plate = anpr_engine.evaluate_vehicle_plate(
        frame_bgr=frame_with_plate,
        vehicle_bbox=v_bbox,
        camera_id="BOP-07",
        track_id=102,
        vehicle_type="CAR",
        force_refresh=True
    )
    print(f"\n    * Test Vehicle #2 (WITH CLEAR PLATE 'DL01AB1234'):")
    print(f"      - plate_detected: {eval_with_plate['plate_detected']}")
    print(f"      - plate_status:   '{eval_with_plate['plate_status']}'")
    print(f"      - plate_text:     '{eval_with_plate['plate_text']}'")
    print(f"      - confidence:     {eval_with_plate['plate_confidence']}%")
    assert eval_with_plate["plate_detected"] is True
    assert eval_with_plate["plate_status"] == "READABLE"
    print("      -> [PASS] Successfully recognized number plate on vehicle crop.")

    print("\n" + "=" * 75)
    print("      ALL VIDEO NUMBER PLATE DETECTION TESTS COMPLETED SUCCESSFULLY")
    print("=" * 75)


if __name__ == "__main__":
    test_plate_detection_on_video()
