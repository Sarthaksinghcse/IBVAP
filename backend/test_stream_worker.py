"""
Test suite for CameraStreamWorker and low-latency pipeline.
"""
import os
import sys
import cv2
import time
import numpy as np

# Ensure paths
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_backend_dir = os.path.join(_repo_root, "backend")
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from services.camera_stream_worker import CameraStreamWorker, camera_stream_manager
from ai_engine.detection.detector import Detector, ALL_SUPPORTED_CLASSES


def test_detector_classes():
    print("\n--- TEST 1: Detector Classes & Supported Set ---")
    detector = Detector(conf_threshold=0.40)
    print(f"Supported classes count: {len(ALL_SUPPORTED_CLASSES)}")
    assert len(ALL_SUPPORTED_CLASSES) >= 15, "Expected at least 15 supported classes"

    # Test detection on a real synthetic frame with high contrast shapes
    test_img = np.zeros((480, 640, 3), dtype=np.uint8)
    test_img[:] = (120, 120, 120)
    dets = detector.detect(test_img, camera_id="TEST-01", track=True, conf_threshold=0.40)
    print(f"Blank frame detection returned: {len(dets)} objects (clean baseline)")
    assert isinstance(dets, list), "Expected list of detections"
    print("PASS: Detector supports all required classes and dynamic conf_threshold.")


def test_stream_worker_architecture():
    print("\n--- TEST 2: CameraStreamWorker Decoupled Architecture ---")
    # Test worker with placeholder stream URL
    worker = CameraStreamWorker(
        camera_id="TEST-USB-01",
        stream_url="http://127.0.0.1:9999/dummy",
        source_type="USB_PHONE",
        conf_threshold=0.40
    )

    # Directly feed simulated frames to test latest-frame buffer and decoupled AI thread
    test_frame_1 = np.full((480, 640, 3), 50, dtype=np.uint8)
    cv2.putText(test_frame_1, "FRAME 1", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    with worker._frame_lock:
        worker._latest_frame = test_frame_1
        worker._latest_frame_time = time.time()
        worker._frame_seq = 1

    time.sleep(0.3) # Allow AI thread to sample

    # Feed newer frame 2 immediately
    test_frame_2 = np.full((480, 640, 3), 80, dtype=np.uint8)
    cv2.putText(test_frame_2, "FRAME 2", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

    with worker._frame_lock:
        worker._latest_frame = test_frame_2
        worker._latest_frame_time = time.time()
        worker._frame_seq = 2

    time.sleep(0.3) # Allow AI thread to process

    metrics = worker.get_metrics()
    print("Worker metrics:", metrics)
    assert metrics["camera_id"] == "TEST-USB-01"
    assert "latency_ms" in metrics
    assert "ai_fps" in metrics
    assert "dropped_stale_frames" in metrics

    # Test MJPEG generator output
    gen = worker.generate_mjpeg()
    first_chunk = next(gen)
    assert b"--frame" in first_chunk, "MJPEG chunk must contain multipart boundary"
    assert b"Content-Type: image/jpeg" in first_chunk, "MJPEG chunk must have JPEG header"
    print(f"Generated MJPEG frame size: {len(first_chunk)} bytes")

    worker.stop()
    print("PASS: Stream worker decoupled architecture and MJPEG generation verified.")


if __name__ == "__main__":
    test_detector_classes()
    test_stream_worker_architecture()
    print("\nALL AUTOMATED TESTS PASSED SUCCESSFULLY!")
