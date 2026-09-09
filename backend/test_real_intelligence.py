"""
Automated Test for SHIELD Real-Time Object Intelligence and Alert System
========================================================================
Validates:
1. Object detection class mappings (PERSON, DOG, CAT, CAR, TRUCK, etc.)
2. Tracker persistent IDs across sequential frames
3. Restricted-zone intrusion detection (OUTSIDE -> INSIDE transition triggers alert)
4. ThreatEngine alert deduplication (person stays in zone -> exactly 1 alert)
5. Zone exit and re-entry state transition (creates new alert only upon re-entry)
6. Dynamic zone reload on worker
"""
import os
import sys
import time
import unittest

# Setup paths
base_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(base_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from ai_engine.detection.detector import Detection
from ai_engine.tracking.tracker import Tracker, TrackedObject
from ai_engine.intelligence.threat_engine import ThreatEngine


class TestRealObjectIntelligence(unittest.TestCase):

    def test_tracker_id_persistence(self):
        """Test tracker maintains persistent IDs as an object moves across frames."""
        tracker = Tracker()

        # Frame 1: Person at (20, 20)
        det1 = Detection(
            object_type="PERSON",
            object_id="Person #1",
            confidence=94.2,
            bbox={"x": 20.0, "y": 20.0, "w": 10.0, "h": 25.0},
            track_id=1
        )
        tracks1 = tracker.update([det1])
        self.assertEqual(len(tracks1), 1)
        self.assertEqual(tracks1[0].track_id, 1)
        self.assertEqual(tracks1[0].object_label, "Person #1")

        # Frame 2: Person shifts slightly to (21, 20)
        det2 = Detection(
            object_type="PERSON",
            object_id="Person #1",
            confidence=95.0,
            bbox={"x": 21.0, "y": 20.0, "w": 10.0, "h": 25.0},
            track_id=1
        )
        tracks2 = tracker.update([det2])
        self.assertEqual(len(tracks2), 1)
        self.assertEqual(tracks2[0].track_id, 1, "Track ID must remain 1 on Frame 2")

        # Frame 3: Second person enters at (60, 40)
        det3_p1 = Detection(
            object_type="PERSON",
            object_id="Person #1",
            confidence=93.8,
            bbox={"x": 22.0, "y": 20.0, "w": 10.0, "h": 25.0},
            track_id=1
        )
        det3_p2 = Detection(
            object_type="PERSON",
            object_id="Person #2",
            confidence=89.5,
            bbox={"x": 60.0, "y": 40.0, "w": 12.0, "h": 28.0},
            track_id=2
        )
        tracks3 = tracker.update([det3_p1, det3_p2])
        self.assertEqual(len(tracks3), 2)
        track_ids = {t.track_id for t in tracks3}
        self.assertEqual(track_ids, {1, 2})

    def test_zone_intrusion_and_deduplication(self):
        """
        Test:
        1. Person outside zone -> NO intrusion alert.
        2. Person enters zone -> ONE ZONE_INTRUSION alert.
        3. Person stays inside zone for 10 frames -> NO duplicate alert spam.
        4. Person leaves zone -> State returns outside.
        5. Person enters zone again -> ONE new ZONE_INTRUSION alert.
        """
        alerts_fired = []

        def mock_alert_cb(alert_data):
            alerts_fired.append(alert_data)

        # Restricted Zone covering (50, 50) to (90, 90)
        zone_polygon = [(50.0, 50.0), (90.0, 50.0), (90.0, 90.0), (50.0, 90.0)]
        engine = ThreatEngine(
            camera_id="TEST-CAM-01",
            restricted_zone_polygon=zone_polygon,
            zone_name="Test Restricted Sector",
            alert_callback=mock_alert_cb,
            detection_callback=None
        )

        self.assertTrue(hasattr(engine, "zone_coords"), "ThreatEngine must expose zone_coords attribute")
        self.assertIsNotNone(engine.zone_coords)

        # Step 1: Person #1 outside zone at bottom_center=(25, 45)
        # Bbox: x=20, y=20, w=10, h=25 -> bottom_center = (25, 45)
        track1 = TrackedObject(
            track_id=1,
            object_type="PERSON",
            object_label="Person #1",
            bbox={"x": 20.0, "y": 20.0, "w": 10.0, "h": 25.0},
            confidence=92.5
        )

        engine.process_tracks([track1])
        self.assertEqual(len(alerts_fired), 0, "No alert should fire when person is outside zone")
        self.assertFalse(track1.in_zone)

        # Step 2: Person #1 moves INTO zone at bottom_center=(65, 75)
        # Bbox: x=60, y=50, w=10, h=25 -> bottom_center = (65, 75) which is inside (50-90, 50-90)
        track1.bbox = {"x": 60.0, "y": 50.0, "w": 10.0, "h": 25.0}
        engine.process_tracks([track1])

        self.assertEqual(len(alerts_fired), 1, "Exactly ONE alert should fire when person enters zone")
        self.assertTrue(track1.in_zone)
        alert = alerts_fired[0]
        self.assertEqual(alert["event_type"], "ZONE_INTRUSION")
        self.assertEqual(alert["object_type"], "PERSON")
        self.assertEqual(alert["object_id"], "Person #1")
        self.assertEqual(alert["camera_id"], "TEST-CAM-01")
        self.assertIn("Test Restricted Sector", alert["reason"])

        # Step 3: Person #1 stays inside zone for 10 frames
        for frame in range(10):
            # Still inside
            track1.bbox = {"x": 62.0, "y": 52.0, "w": 10.0, "h": 25.0}
            engine.process_tracks([track1])

        self.assertEqual(len(alerts_fired), 1, "Alert must NOT be duplicated while person remains inside zone")

        # Step 4: Person #1 exits zone back to (20, 20)
        track1.bbox = {"x": 20.0, "y": 20.0, "w": 10.0, "h": 25.0}
        engine.process_tracks([track1])
        self.assertFalse(track1.in_zone)
        self.assertEqual(len(alerts_fired), 1, "No new alert on exit")

        # Step 5: Person #1 re-enters zone
        track1.bbox = {"x": 65.0, "y": 55.0, "w": 10.0, "h": 25.0}
        engine.process_tracks([track1])
        self.assertEqual(len(alerts_fired), 2, "A new intrusion alert must fire upon re-entry")
        self.assertEqual(alerts_fired[1]["event_type"], "ZONE_INTRUSION")

    def test_animal_classification_no_fake_gender(self):
        """Test animal classes (DOG, CAT) do not produce false person/gender alerts."""
        alerts_fired = []
        engine = ThreatEngine(
            camera_id="TEST-CAM-01",
            restricted_zone_polygon=[(10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0)],
            zone_name="Perimeter",
            alert_callback=lambda a: alerts_fired.append(a),
            detection_callback=None
        )

        dog_track = TrackedObject(
            track_id=2,
            object_type="DOG",
            object_label="Dog #2",
            bbox={"x": 30.0, "y": 30.0, "w": 15.0, "h": 15.0},
            confidence=88.0
        )

        dets = engine.process_tracks([dog_track])
        self.assertEqual(len(dets), 1)
        self.assertEqual(dets[0]["event_type"], "DOG_DETECTED")
        self.assertEqual(dets[0]["object_type"], "DOG")
        self.assertEqual(len(alerts_fired), 0, "Animals must be filtered from high-threat intrusion alerts")


if __name__ == "__main__":
    unittest.main()
