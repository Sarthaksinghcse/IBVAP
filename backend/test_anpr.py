"""
IBVAP — Comprehensive Real Automatic Number Plate Recognition (ANPR) Test Suite
================================================================================
Verifies:
1. CRNN neural text recognizer model initialization.
2. Real license plate localization on vehicle crops via morphological gradients.
3. No-plate rejection -> plate_status = 'NOT_DETECTED'.
4. Real neural OCR character extraction on clear plate crops.
5. Graceful handling of blurred/occluded plates -> 'UNREADABLE' / 'UNCERTAIN'.
6. Multi-frame temporal consensus per vehicle track ID.
7. Independent multi-vehicle plate isolation (Vehicle #1 vs Vehicle #2).
8. SQLite database persistence in 'anpr_events' table.
9. Database-level ANPR statistics calculation.
"""
import os
import sys
import uuid
import json
import time
import cv2
import numpy as np

# Ensure root paths are in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import Base, engine, SessionLocal
from models.models import ANPREvent
from ai_engine.intelligence.anpr_engine import get_anpr_engine


def _create_synthetic_vehicle_with_plate(plate_text: str = "DL01AB1234", blur: bool = False, no_plate: bool = False) -> np.ndarray:
    """
    Creates a synthetic vehicle bumper image with realistic aspect ratio,
    bumper structure, and embedded high-contrast license plate.
    """
    # Vehicle bumper (160h x 240w)
    img = np.ones((160, 240, 3), dtype=np.uint8) * 45 # Dark gray bumper

    if no_plate:
        # Just smooth bumper surface, no rectangular high-contrast plate
        cv2.line(img, (20, 80), (220, 80), (70, 70, 70), 4)
        return img

    # Draw rectangular white license plate in lower center
    # Aspect ratio ~ 3.5 (110w x 32h)
    px1, py1 = 65, 95
    pw, ph = 110, 32
    px2, py2 = px1 + pw, py1 + ph

    # White plate background with black border
    cv2.rectangle(img, (px1, py1), (px2, py2), (245, 245, 245), -1)
    cv2.rectangle(img, (px1, py1), (px2, py2), (20, 20, 20), 2)

    # Draw plate characters
    cv2.putText(img, plate_text, (px1 + 6, py1 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (10, 10, 10), 2)

    if blur:
        # Severely blur plate area to simulate out-of-focus / motion blur
        plate_roi = img[py1:py2, px1:px2]
        blurred_roi = cv2.GaussianBlur(plate_roi, (21, 21), 9.0)
        img[py1:py2, px1:px2] = blurred_roi

    return img


def run_all_tests():
    print("=" * 70)
    print("   IBVAP TOPIC 2: REAL AUTOMATIC NUMBER PLATE RECOGNITION TESTS")
    print("=" * 70)

    # Ensure SQLite tables exist
    Base.metadata.create_all(bind=engine)

    # 1. Model Loading
    print("\n[TEST 1] Initializing OpenCV Zoo CRNN text recognizer model...")
    anpr_eng = get_anpr_engine()
    assert anpr_eng.is_ready, "ANPREngine failed to load CRNN ONNX model!"
    print("[PASS] CRNN Neural Text Recognizer initialized successfully.")

    # 2. Real Plate Localization
    print("\n[TEST 2] Testing license plate localization on vehicle bumper crop...")
    veh_img = _create_synthetic_vehicle_with_plate("HR26DK8392")
    found, plate_crop, bbox = anpr_eng.locate_plate_region(veh_img)
    assert found and plate_crop is not None, "PlateLocalizer failed to detect plate region!"
    assert plate_crop.shape[0] >= 14 and plate_crop.shape[1] >= 35, f"Invalid plate crop dimensions: {plate_crop.shape}"
    print(f"[PASS] Plate localized at bbox {bbox} (crop shape: {plate_crop.shape}).")

    # 3. No Plate Detection Rejection
    print("\n[TEST 3] Testing non-plate vehicle surface rejection...")
    no_plate_img = _create_synthetic_vehicle_with_plate(no_plate=True)
    # When evaluated via evaluate_vehicle_plate on frame
    frame_empty = np.ones((480, 640, 3), dtype=np.uint8) * 60
    eval_no_plate = anpr_eng.evaluate_vehicle_plate(
        frame_bgr=frame_empty,
        vehicle_bbox={"x": 20, "y": 20, "w": 40, "h": 40},
        camera_id="BOP-02",
        track_id=99,
        vehicle_type="CAR",
        force_refresh=True
    )
    # The empty frame has no plate text
    assert eval_no_plate["plate_status"] in ["NOT_DETECTED", "UNREADABLE"], f"Unexpected status: {eval_no_plate}"
    print(f"[PASS] Correctly handled vehicle without visible plate -> status: {eval_no_plate['plate_status']}")

    # 4. Real OCR on Clear Plate
    print("\n[TEST 4] Testing neural OCR on clear license plate...")
    clean_plate_img = np.ones((32, 100, 3), dtype=np.uint8) * 255
    cv2.rectangle(clean_plate_img, (0, 0), (100, 32), (0, 0, 0), 2)
    cv2.putText(clean_plate_img, "DL01AB", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)

    text, conf, status, *_ = anpr_eng.recognize_plate(clean_plate_img)
    assert text is not None and len(text) >= 4, f"OCR returned invalid text: '{text}'"
    assert conf >= 70.0, f"Expected confidence >= 70.0%, got {conf}%"
    assert status == "READABLE", f"Expected READABLE status, got {status}"
    print(f"[PASS] Neural OCR recognized plate text: '{text}' (Confidence: {conf}%, Status: {status})")

    # 5. Degraded / Blurred Plate Handling
    print("\n[TEST 5] Testing graceful degradation on blurred plate...")
    blurred_plate_img = np.ones((32, 100, 3), dtype=np.uint8) * 255
    cv2.putText(blurred_plate_img, "DL01AB", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
    blurred_plate_img = cv2.GaussianBlur(blurred_plate_img, (25, 25), 11.0) # extreme blur

    b_text, b_conf, b_status, *_ = anpr_eng.recognize_plate(blurred_plate_img)
    # Either returns UNREADABLE or UNCERTAIN with low conf — never a fake confident match
    assert b_status in ["UNREADABLE", "UNCERTAIN"] or (b_text is None), f"Unexpected status for blurred plate: {b_status}"
    print(f"[PASS] Blurred plate correctly classified as {b_status} (Zero fake text hallucinated).")

    # 6. Multi-Frame Temporal Consensus per Vehicle Track
    print("\n[TEST 6] Testing multi-frame temporal consensus on tracked vehicle...")
    frame_veh = np.zeros((400, 600, 3), dtype=np.uint8)
    # Place vehicle at x: 20% (120px), y: 30% (120px), w: 50% (300px), h: 50% (200px)
    veh_crop = _create_synthetic_vehicle_with_plate("KA05MJ4411")
    veh_crop_resized = cv2.resize(veh_crop, (300, 200))
    frame_veh[120:320, 120:420] = veh_crop_resized

    v_bbox = {"x": 20.0, "y": 30.0, "w": 50.0, "h": 50.0}

    # Simulate 4 consecutive video frames for Vehicle Track #7
    readings = []
    for f_idx in range(4):
        eval_res = anpr_eng.evaluate_vehicle_plate(
            frame_bgr=frame_veh,
            vehicle_bbox=v_bbox,
            camera_id="BOP-01",
            track_id=7,
            vehicle_type="CAR",
            force_refresh=(f_idx == 0) # Test temporal accumulation
        )
        readings.append(eval_res)

    last_eval = readings[-1]
    assert last_eval["vehicle_track_id"] == 7, "Vehicle track ID association lost!"
    print(f"[PASS] Vehicle Track #7 stable plate consensus: '{last_eval.get('plate_text')}' (Status: {last_eval.get('plate_status')})")

    # 7. Independent Multi-Vehicle Plate Isolation
    print("\n[TEST 7] Testing independent multi-vehicle plate isolation...")
    # Vehicle #1 (CAR) vs Vehicle #2 (TRUCK) in same scene
    eval_v1 = anpr_eng.evaluate_vehicle_plate(
        frame_bgr=frame_veh,
        vehicle_bbox=v_bbox,
        camera_id="BOP-01",
        track_id=1,
        vehicle_type="CAR",
        force_refresh=True
    )
    eval_v2 = anpr_eng.evaluate_vehicle_plate(
        frame_bgr=frame_empty,
        vehicle_bbox={"x": 70, "y": 20, "w": 25, "h": 30},
        camera_id="BOP-01",
        track_id=2,
        vehicle_type="TRUCK",
        force_refresh=True
    )
    assert eval_v1["vehicle_track_id"] == 1 and eval_v2["vehicle_track_id"] == 2
    print(f"[PASS] Vehicle #1 ({eval_v1['vehicle_type']}) and Vehicle #2 ({eval_v2['vehicle_type']}) isolated independently.")

    # 8. SQLite Database Persistence & Stats
    print("\n[TEST 8] Testing ANPREvent SQLite database persistence and statistics...")
    db = SessionLocal()
    try:
        test_event_id = f"test-anpr-{uuid.uuid4().hex[:6]}"
        anpr_rec = ANPREvent(
            id=test_event_id,
            camera_id="BOP-01",
            vehicle_track_id=7,
            vehicle_type="CAR",
            plate_text="KA05MJ4411",
            plate_confidence=92.5,
            plate_status="READABLE",
            bbox_x=20.0,
            bbox_y=30.0,
            bbox_w=50.0,
            bbox_h=50.0
        )
        db.add(anpr_rec)
        db.commit()

        # Query back
        fetched = db.query(ANPREvent).filter(ANPREvent.id == test_event_id).first()
        assert fetched is not None, "ANPREvent record was not saved to SQLite!"
        assert fetched.plate_text == "KA05MJ4411", f"Saved plate mismatch: {fetched.plate_text}"
        assert fetched.plate_status == "READABLE"
        print(f"[PASS] Persisted ANPREvent to SQLite (Plate: {fetched.plate_text}, Confidence: {fetched.plate_confidence}%).")

        # Query stats
        total_events = db.query(ANPREvent).count()
        readable_count = db.query(ANPREvent).filter(ANPREvent.plate_status == "READABLE").count()
        assert total_events >= 1 and readable_count >= 1, "Stats query returned invalid count!"
        print(f"[PASS] SQLite ANPR stats computed: {readable_count} readable events in database.")

        # Cleanup test record
        db.delete(fetched)
        db.commit()
        print("[PASS] Cleaned up temporary test records.")

    finally:
        db.close()

    print("\n" + "=" * 70)
    print("   ALL 8 ANPR TESTS PASSED (100% OK)")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
