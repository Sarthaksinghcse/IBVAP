import sys, os
import unittest
import json

# Add project root and backend root
backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi.testclient import TestClient
from main import app
from database.database import SessionLocal, engine, Base
from models.models import Zone, Camera, Alert, Detection
from ai_engine.intelligence.threat_engine import ThreatEngine
from ai_engine.tracking.tracker import TrackedObject


class TestCameraSpecificZones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_01_zone_crud_endpoints(self):
        """Test REST API CRUD for source-specific zones."""
        # 1. Create zone for BOP-02
        bop02_coords = [[10.0, 10.0], [50.0, 10.0], [50.0, 80.0], [10.0, 80.0]]
        res = self.client.post("/api/zones/", json={
            "source_id": "BOP-02",
            "source_type": "CAMERA",
            "name": "Perimeter West Zone",
            "coordinates": bop02_coords,
            "enabled": True,
            "zone_type": "RESTRICTED"
        })
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["source_id"], "BOP-02")
        self.assertEqual(data["name"], "Perimeter West Zone")
        self.assertEqual(len(data["coordinates"]), 4)

        # 2. Get BOP-02 zone
        get_res = self.client.get("/api/zones/BOP-02")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["name"], "Perimeter West Zone")

        # 3. Create distinct zone for WEBCAM-01
        webcam_coords = [[20.0, 20.0], [80.0, 20.0], [80.0, 80.0], [20.0, 80.0]]
        webcam_res = self.client.post("/api/zones/", json={
            "source_id": "WEBCAM-01",
            "source_type": "WEBCAM",
            "name": "Webcam Monitored Doorway",
            "coordinates": webcam_coords,
            "enabled": True,
            "zone_type": "RESTRICTED"
        })
        self.assertEqual(webcam_res.status_code, 200)
        self.assertEqual(webcam_res.json()["source_id"], "WEBCAM-01")

        # Verify BOP-02 and WEBCAM-01 have DIFFERENT coordinates
        self.assertNotEqual(get_res.json()["coordinates"], webcam_res.json()["coordinates"])

        # 4. Query nonexistent source returns 404
        bad_res = self.client.get("/api/zones/NON_EXISTENT_CAM")
        self.assertEqual(bad_res.status_code, 404)

        # 5. Delete BOP-02 zone
        del_res = self.client.delete("/api/zones/BOP-02")
        self.assertEqual(del_res.status_code, 200)
        get_deleted = self.client.get("/api/zones/BOP-02")
        self.assertEqual(get_deleted.status_code, 404)

    def test_02_threat_engine_zone_isolation(self):
        """Test ThreatEngine evaluates objects ONLY against its source-configured zone."""
        # Setup: ThreatEngine A with BOP-01 zone (5,5 to 45,95)
        engine_bop01 = ThreatEngine(
            camera_id="BOP-01",
            loitering_threshold=10.0,
            restricted_zone_polygon=[(5.0, 5.0), (45.0, 5.0), (45.0, 95.0), (5.0, 95.0)],
            zone_name="Restricted Zone A"
        )

        # Setup: ThreatEngine B with NO zone configured (None)
        engine_bop02 = ThreatEngine(
            camera_id="BOP-02",
            loitering_threshold=10.0,
            restricted_zone_polygon=None,
            zone_name=None
        )

        # Tracked person in the left sector (x=20, y=50, bottom_center=(25, 70))
        track_left = TrackedObject(
            track_id=1,
            object_type="PERSON",
            object_label="Person #1",
            bbox={"x": 20.0, "y": 50.0, "w": 10.0, "h": 20.0},
            confidence=88.5
        )

        # 1. BOP-01 with zone should identify INTRUSION
        dets_bop01 = engine_bop01.process_tracks([track_left])
        self.assertEqual(len(dets_bop01), 1)
        self.assertTrue(dets_bop01[0]["is_in_restricted_zone"])
        self.assertEqual(dets_bop01[0]["event_type"], "ZONE_INTRUSION")
        self.assertEqual(dets_bop01[0]["zone"], "Restricted Zone A")

        # 2. BOP-02 without zone should NOT identify intrusion for the same coordinates
        track_left_bop02 = TrackedObject(
            track_id=1,
            object_type="PERSON",
            object_label="Person #1",
            bbox={"x": 20.0, "y": 50.0, "w": 10.0, "h": 20.0},
            confidence=88.5
        )
        dets_bop02 = engine_bop02.process_tracks([track_left_bop02])
        self.assertEqual(len(dets_bop02), 1)
        self.assertFalse(dets_bop02[0]["is_in_restricted_zone"])
        self.assertEqual(dets_bop02[0]["event_type"], "PERSON_DETECTED")
        self.assertIsNone(dets_bop02[0]["zone"])

    def test_03_webcam_isolated_threat_evaluation(self):
        """Test WEBCAM-01 uses its own zone geometry."""
        engine_webcam = ThreatEngine(
            camera_id="WEBCAM-01",
            loitering_threshold=15.0,
            restricted_zone_polygon=[(60.0, 10.0), (90.0, 10.0), (90.0, 90.0), (60.0, 90.0)],
            zone_name="Webcam Monitored Area"
        )

        # Track at left sector (x=10, y=20, bottom_center=(15, 40)) -> Outside webcam zone
        track_outside = TrackedObject(
            track_id=2,
            object_type="PERSON",
            object_label="Person #2",
            bbox={"x": 10.0, "y": 20.0, "w": 10.0, "h": 20.0},
            confidence=92.0
        )
        dets_out = engine_webcam.process_tracks([track_outside])
        self.assertFalse(dets_out[0]["is_in_restricted_zone"])

        # Track at right sector (x=70, y=40, bottom_center=(75, 60)) -> Inside webcam zone
        track_inside = TrackedObject(
            track_id=3,
            object_type="PERSON",
            object_label="Person #3",
            bbox={"x": 70.0, "y": 40.0, "w": 10.0, "h": 20.0},
            confidence=94.0
        )
        dets_in = engine_webcam.process_tracks([track_inside])
        self.assertTrue(dets_in[0]["is_in_restricted_zone"])
        self.assertEqual(dets_in[0]["zone"], "Webcam Monitored Area")


if __name__ == "__main__":
    unittest.main()
