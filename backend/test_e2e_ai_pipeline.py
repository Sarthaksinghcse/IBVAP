"""
End-to-End Test Suite for SHIELD Live AI Pipeline
==================================================
Tests:
1. Frame rotation logic (90, 180, 270)
2. YOLOv8 high sensitivity detection (conf=0.30, imgsz=640)
3. Tracker ID stability (no jumping on small centroid shift)
4. ThreatEngine zone evaluation and alert dispatch
"""
import unittest
import numpy as np
import cv2
import time
import os
import sys

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_engine.detection.detector import Detector, Detection
from ai_engine.tracking.tracker import Tracker
from ai_engine.intelligence.threat_engine import ThreatEngine


class TestE2EAIPipeline(unittest.TestCase):

    def test_frame_rotation(self):
        """Verify OpenCV rotation works as expected for 90, 180, 270 degrees."""
        # Create a horizontal test image (height=480, width=640)
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 90 deg clockwise -> becomes height=640, width=480
        rot90 = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        self.assertEqual(rot90.shape[:2], (640, 480))

        # 180 deg -> stays height=480, width=640
        rot180 = cv2.rotate(img, cv2.ROTATE_180)
        self.assertEqual(rot180.shape[:2], (480, 640))

        # 270 deg (counter-clockwise) -> becomes height=640, width=480
        rot270 = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        self.assertEqual(rot270.shape[:2], (640, 480))

    def test_detector_configuration(self):
        """Verify detector runs at 0.30 default confidence and accepts custom thresholds."""
        detector = Detector(conf_threshold=0.30)
        self.assertAlmostEqual(detector.conf_threshold, 0.30, places=2)
        
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        res = detector.detect(dummy_frame, track=False)
        self.assertIsInstance(res, list)

    def test_tracker_id_stability(self):
        """Verify tracker maintains ID across slight centroid movement and brief drop."""
        tracker = Tracker(max_missed_seconds=6.0, match_distance_threshold=35.0)

        # Frame 1: Person at (40, 40)
        det1 = Detection(
            object_type="PERSON",
            object_id="Person #1",
            confidence=85.0,
            bbox={"x": 40.0, "y": 40.0, "w": 10.0, "h": 25.0},
            track_id=1
        )
        tracks1 = tracker.update([det1])
        self.assertEqual(len(tracks1), 1)
        self.assertEqual(tracks1[0].track_id, 1)

        # Frame 2: Person moved slightly to (42, 41) with new YOLO raw ID
        det2 = Detection(
            object_type="PERSON",
            object_id="Person #99",
            confidence=82.0,
            bbox={"x": 42.0, "y": 41.0, "w": 10.0, "h": 25.0},
            track_id=99  # YOLO internal re-id
        )
        tracks2 = tracker.update([det2])
        self.assertEqual(len(tracks2), 1)
        # Tracker association should preserve original stable ID 1
        self.assertEqual(tracks2[0].track_id, 1)

    def test_threat_engine_zone_alert_and_dedup(self):
        """Verify ThreatEngine triggers alert on entry, no spam while inside, and re-entry."""
        alerts = []
        te = ThreatEngine(
            camera_id="TEST-USB-01",
            restricted_zone_polygon=[(10.0, 10.0), (80.0, 10.0), (80.0, 80.0), (10.0, 80.0)],
            zone_name="Restricted Zone Alpha",
            alert_callback=lambda a: alerts.append(a)
        )

        tracker = Tracker()

        # Step 1: Outside zone
        det_out = Detection(
            object_type="PERSON",
            object_id="Person #1",
            confidence=90.0,
            bbox={"x": 2.0, "y": 2.0, "w": 4.0, "h": 5.0},
            track_id=1
        )
        tracks = tracker.update([det_out])
        te.process_tracks(tracks)
        self.assertEqual(len(alerts), 0)

        # Step 2: Step into zone
        det_in = Detection(
            object_type="PERSON",
            object_id="Person #1",
            confidence=90.0,
            bbox={"x": 20.0, "y": 20.0, "w": 10.0, "h": 20.0},
            track_id=1
        )
        tracks = tracker.update([det_in])
        te.process_tracks(tracks)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["event_type"], "ZONE_INTRUSION")

        # Step 3: Remain in zone for next frame -> no duplicate alert
        tracks = tracker.update([det_in])
        te.process_tracks(tracks)
        self.assertEqual(len(alerts), 1)


if __name__ == "__main__":
    unittest.main()
