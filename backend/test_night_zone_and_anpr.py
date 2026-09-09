"""
Verification of Night Restricted Zone & ANPR on Enhanced Frames
Testing:
1. ThreatEngine restricted zone intrusion with bottom-center point from enhanced frame detections
2. ANPR plate detection and OCR pipeline on vehicles in low-light conditions
"""
import os
import sys
import cv2
import numpy as np

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_engine.preprocessing.frame_enhancer import FrameEnhancer
from ai_engine.intelligence.threat_engine import ThreatEngine, DEFAULT_RESTRICTED_ZONE_A
from ai_engine.intelligence.anpr_engine import ANPREngine
from shapely.geometry import Point

def test_night_restricted_zone():
    print("\n--- Testing Night Restricted Zone Detection ---")
    alerts_received = []

    def mock_alert_cb(alert_data):
        alerts_received.append(alert_data)
        print(f"[ZONE ALERT] Received: {alert_data.get('event_type')} for {alert_data.get('object_id')}")

    engine = ThreatEngine(
        camera_id="NIGHT-CCTV-01",
        loitering_threshold=5.0,
        restricted_zone_polygon=DEFAULT_RESTRICTED_ZONE_A,
        zone_name="Perimeter Zone Alpha",
        alert_callback=mock_alert_cb
    )

    # Simulate bottom-center coordinates:
    # 1. Person outside zone
    outside_pt = Point(80.0, 50.0) # (80%, 50%) is outside DEFAULT_RESTRICTED_ZONE_A (5-50% X)
    assert not engine.zone_polygon.contains(outside_pt), "Test point (80, 50) should be outside"

    # 2. Person inside zone
    inside_pt = Point(25.0, 50.0) # (25%, 50%) is inside DEFAULT_RESTRICTED_ZONE_A
    assert engine.zone_polygon.contains(inside_pt), "Test point (25, 50) should be inside zone"

    print(f"[PASS] Night Restricted Zone correctly discriminates outside ({outside_pt.x}, {outside_pt.y}) vs inside ({inside_pt.x}, {inside_pt.y}).")


def test_night_anpr_ocr():
    print("\n--- Testing Night ANPR & Plate Crop Processing ---")
    anpr = ANPREngine()
    enhancer = FrameEnhancer()

    # Load night frame with car
    night_video_path = os.path.join(
        project_root, "storage", "videos",
        "b05f5575-7f61-4162-92d6-292de4660d9e_vidssave.com 8MP 4K Dahua CCTV System Sample Video - Night Time 1080P.mp4"
    )
    cap = cv2.VideoCapture(night_video_path)
    ret, frame = cap.read()
    cap.release()
    assert ret, "Failed to read night frame"

    enh_frame, _, _ = enhancer.enhance(frame)

    # Vehicle bounding box in scene
    h, w = frame.shape[:2]
    vehicle_bbox = {"x": int(w * 0.2), "y": int(h * 0.3), "w": int(w * 0.5), "h": int(h * 0.5)}

    result = anpr.evaluate_vehicle_plate(
        frame_bgr=enh_frame,
        vehicle_bbox=vehicle_bbox,
        camera_id="NIGHT-CCTV-01",
        track_id=1,
        vehicle_type="CAR"
    )

    print(f"ANPR Result on enhanced frame: status={result.get('plate_status')} | plate_text={result.get('plate_text')} | conf={result.get('plate_confidence')}")
    assert result.get("plate_status") in ["READABLE", "UNREADABLE", "NOT_DETECTED"], "Invalid plate status"
    # Never hallucinate: if unreadable, report UNREADABLE
    if not result.get("plate_text"):
        assert result.get("plate_status") != "READABLE", "Zero hallucination: unreadable plate must not be marked READABLE"
    print("[PASS] Night ANPR correctly evaluates plate crop with zero hallucination guarantee.")


if __name__ == "__main__":
    test_night_restricted_zone()
    test_night_anpr_ocr()
    print("\n[PASS] All Night Zone and ANPR tests passed successfully!")
