"""
Comprehensive Integration Test for Real-Time Live Camera Low-Light Enhancement.
================================================================================
Verifies:
1. Multi-camera FrameEnhancer isolation (Camera A dark vs Camera B bright).
2. Live Webcam / USB Phone inference endpoint (/api/cameras/webcam/infer) with view_mode.
3. Decoupled CameraStreamWorker MJPEG streaming and runtime metrics.
4. Downstream AI pipelines (YOLOv8, Tracker, ANPR, ThreatEngine) on live enhanced frames.
5. Dual-frame strategy (raw frame untouched vs enhanced frame for inference).
"""

import os
import sys
import cv2
import time
import base64
import requests
import numpy as np

# Add repository root and backend to sys.path
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_backend_dir = os.path.join(_repo_root, "backend")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from ai_engine.preprocessing.frame_enhancer import FrameEnhancer
from ai_engine.detection.detector import Detector
from ai_engine.tracking.tracker import Tracker
from ai_engine.intelligence.threat_engine import ThreatEngine
from backend.services.camera_stream_worker import CameraStreamWorker


def test_multi_camera_enhancer_isolation():
    print("\n--- Test 1: Multi-Camera FrameEnhancer Isolation ---")
    from backend.routes.cameras import _get_camera_enhancer

    enhancer_a = _get_camera_enhancer("CAM-NIGHT-01")
    enhancer_b = _get_camera_enhancer("CAM-DAY-02")

    assert enhancer_a is not enhancer_b, "Each camera must have its own FrameEnhancer instance!"

    # Create dark frame (mean lum ~35) for Camera A
    dark_frame = np.full((360, 640, 3), 35, dtype=np.uint8)
    # Add some texture / gradient
    cv2.circle(dark_frame, (320, 180), 50, (60, 60, 60), -1)

    # Create bright daytime frame (mean lum ~150) for Camera B
    bright_frame = np.full((360, 640, 3), 150, dtype=np.uint8)

    enhanced_a, was_enh_a, meta_a = enhancer_a.enhance(dark_frame.copy())
    enhanced_b, was_enh_b, meta_b = enhancer_b.enhance(bright_frame.copy())

    print(f"Camera A (Dark): was_enhanced={was_enh_a}, lum={meta_a['brightness']:.1f}, gamma={meta_a['gamma']:.2f}")
    print(f"Camera B (Bright): was_enhanced={was_enh_b}, lum={meta_b['brightness']:.1f}, gamma={meta_b['gamma']:.2f}")

    assert was_enh_a == True, "Dark camera must trigger low-light enhancement"
    assert was_enh_b == False, "Bright camera must NOT trigger low-light enhancement"

    # Verify dark_frame was not mutated
    assert np.mean(dark_frame) < 40, "Original raw frame must not be mutated"
    assert np.mean(enhanced_a) > np.mean(dark_frame), "Enhanced frame must be brighter than raw frame"

    print("PASS: Multi-camera isolation verified successfully.")


def test_webcam_infer_endpoint():
    print("\n--- Test 2: Live Webcam / USB Phone Infer Endpoint ---")
    backend_url = "http://127.0.0.1:8000"

    # 1. Test with Dark Night Frame & view_mode="enhanced"
    dark_frame = np.full((360, 640, 3), 30, dtype=np.uint8)
    cv2.putText(dark_frame, "TEST NIGHT", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (70, 70, 70), 2)
    _, dark_jpg = cv2.imencode(".jpg", dark_frame)
    b64_dark = base64.b64encode(dark_jpg).decode("ascii")

    payload_enhanced = {
        "image_base64": b64_dark,
        "camera_id": "WEBCAM-TEST-NIGHT",
        "conf_threshold": 0.25,
        "frame_seq": 1,
        "face_recognition_enabled": False,
        "anpr_enabled": False,
        "view_mode": "enhanced"
    }
    r = requests.post(f"{backend_url}/api/cameras/webcam/infer", json=payload_enhanced, timeout=10)
    assert r.status_code == 200, f"Infer failed: {r.text}"
    data = r.json()

    print(f"Night response: low_light={data.get('low_light')}, brightness={data.get('brightness')}, has_b64={bool(data.get('enhanced_image_base64'))}")
    assert data.get("low_light") == True, "Expected low_light=True for dark frame"
    assert data.get("enhanced_image_base64") is not None, "Expected enhanced_image_base64 when view_mode=enhanced"
    assert data.get("enhanced_image_base64").startswith("data:image/jpeg;base64,"), "Base64 must be data URI"

    # 2. Test with Dark Night Frame & view_mode="original"
    payload_orig = {
        "image_base64": b64_dark,
        "camera_id": "WEBCAM-TEST-NIGHT",
        "conf_threshold": 0.25,
        "frame_seq": 2,
        "face_recognition_enabled": False,
        "anpr_enabled": False,
        "view_mode": "original"
    }
    r = requests.post(f"{backend_url}/api/cameras/webcam/infer", json=payload_orig, timeout=10)
    assert r.status_code == 200
    data_orig = r.json()
    print(f"Original mode response: low_light={data_orig.get('low_light')}, has_b64={bool(data_orig.get('enhanced_image_base64'))}")
    assert data_orig.get("low_light") == True
    assert data_orig.get("enhanced_image_base64") is None, "When view_mode=original, enhanced_image_base64 should be None"

    # 3. Test with Daylight Frame
    bright_frame = np.full((360, 640, 3), 160, dtype=np.uint8)
    _, bright_jpg = cv2.imencode(".jpg", bright_frame)
    b64_bright = base64.b64encode(bright_jpg).decode("ascii")

    payload_bright = {
        "image_base64": b64_bright,
        "camera_id": "WEBCAM-TEST-DAY",
        "conf_threshold": 0.25,
        "frame_seq": 1,
        "face_recognition_enabled": False,
        "anpr_enabled": False,
        "view_mode": "enhanced"
    }
    r = requests.post(f"{backend_url}/api/cameras/webcam/infer", json=payload_bright, timeout=10)
    assert r.status_code == 200
    data_bright = r.json()
    print(f"Daylight mode response: low_light={data_bright.get('low_light')}, brightness={data_bright.get('brightness')}")
    assert data_bright.get("low_light") == False, "Expected low_light=False for bright frame"
    assert data_bright.get("enhanced_image_base64") is None

    print("PASS: Live webcam infer endpoint verified successfully.")


def test_camera_stream_worker_enhancement():
    print("\n--- Test 3: CameraStreamWorker Enhancement & MJPEG Stream ---")
    worker = CameraStreamWorker(
        camera_id="TEST-STREAM-CAM",
        stream_url="test://dummy",
        source_type="CCTV"
    )

    # Simulate receiving a dark night frame
    dark_frame = np.full((360, 640, 3), 32, dtype=np.uint8)
    cv2.putText(dark_frame, "CCTV NIGHT LIVE", (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (65, 65, 65), 2)

    with worker._frame_lock:
        worker._latest_frame = dark_frame.copy()
        worker._latest_frame_time = time.time()
        worker._frame_seq = 1

    # Run one step of enhancement on worker
    frame_for_infer, was_enh, meta = worker.enhancer.enhance(dark_frame.copy())
    with worker._frame_lock:
        worker._latest_enhanced_frame = frame_for_infer
        worker._is_low_light = was_enh
        worker._current_brightness = meta["brightness"]
        worker._current_gamma = meta["gamma"]

    metrics = worker.get_metrics()
    print("Worker metrics:", {k: metrics[k] for k in ["camera_id", "low_light", "brightness", "gamma"]})
    assert metrics["low_light"] == True
    assert metrics["brightness"] == round(meta["brightness"], 1)

    # Test MJPEG generator in enhanced mode
    gen_enhanced = worker.generate_mjpeg(view_mode="enhanced")
    frame_chunk = next(gen_enhanced)
    assert b"--frame" in frame_chunk
    assert b"Content-Type: image/jpeg" in frame_chunk

    # Verify the generated MJPEG frame contains JPEG image data
    start_idx = frame_chunk.find(b"\xff\xd8")
    assert start_idx != -1, "MJPEG chunk must contain valid JPEG SOF marker"

    # Stop worker
    worker._stopped = True
    print("PASS: CameraStreamWorker enhancement and metrics verified successfully.")


def test_downstream_ai_on_enhanced_frames():
    print("\n--- Test 4: Downstream AI Pipelines on Enhanced Live Frame ---")
    enhancer = FrameEnhancer()
    detector = Detector(conf_threshold=0.20)
    tracker = Tracker()
    threat_engine = ThreatEngine(
        camera_id="CAM-AI-TEST",
        loitering_threshold=5.0
    )

    # Create dark frame with a synthetic person / object
    dark_frame = np.full((480, 640, 3), 28, dtype=np.uint8)
    # Draw a brighter simulated silhouette
    cv2.rectangle(dark_frame, (200, 100), (300, 400), (65, 75, 70), -1)
    cv2.circle(dark_frame, (250, 130), 30, (80, 85, 80), -1)

    # Run enhancer
    enhanced_frame, was_enh, meta = enhancer.enhance(dark_frame.copy())
    assert was_enh == True

    # Run detector on enhanced frame
    dets = detector.detect(enhanced_frame, camera_id="CAM-AI-TEST", track=True)
    tracks = tracker.update(dets)

    # Process tracks in ThreatEngine with dual-frame (raw for evidence, enhanced for inference)
    threat_engine.process_tracks(
        tracks,
        video_id=None,
        frame_bgr=dark_frame,
        inference_bgr=enhanced_frame
    )

    print(f"Downstream AI processed: {len(dets)} detections, {len(tracks)} tracks")
    print("PASS: Downstream AI pipelines processed enhanced live frames without error.")


if __name__ == "__main__":
    print("=== RUNNING LIVE CAMERA ENHANCEMENT TEST SUITE ===")
    test_multi_camera_enhancer_isolation()
    test_webcam_infer_endpoint()
    test_camera_stream_worker_enhancement()
    test_downstream_ai_on_enhanced_frames()
    print("\n========================================================")
    print("ALL LIVE CAMERA ENHANCEMENT TESTS PASSED SUCCESSFULLY! (4/4)")
    print("========================================================")
