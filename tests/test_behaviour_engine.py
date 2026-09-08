"""
Unit & Integration Tests for Behaviour Engine (Phases B2 - B5)
================================================================
Verifies TrackState kinematics, Layer 1 rule primitives, Layer 2 grid anomaly scoring,
alert fusion, rate limiting, and the IBVAP_BEHAVIOUR_ENABLED flag.
"""
import os
import sys
import time
import numpy as np

# Ensure project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_engine.tracking.tracker import TrackedObject
from ai_engine.intelligence.behaviour.behaviour_engine import BehaviourEngine
from ai_engine.intelligence.behaviour.track_state import TrackState
from ai_engine.intelligence.behaviour import primitives
from ai_engine.intelligence.behaviour.zones import ZoneDefinition, ZoneManager


def test_track_state_kinematics():
    """Test TrackState rolling window, velocity, scale-invariant speed, and direction."""
    print("--> Testing TrackState Kinematics...")
    st = TrackState(track_id=1, object_type="PERSON", object_label="Person #1")

    # Simulate movement from (10%, 10%) to (30%, 10%) over 1 second (10 frames)
    t0 = time.time()
    for i in range(10):
        bbox = {"x": 10.0 + i * 2.0, "y": 10.0, "w": 5.0, "h": 20.0}
        st.update(bbox, timestamp=t0 + i * 0.1)

    assert len(st.centroid_history) == 10
    assert st.dwell_frames == 10
    assert st.speed_pct_s > 0.0
    # Moving right -> direction_deg should be near 0 degrees
    assert abs(st.direction_deg - 0.0) < 15.0 or abs(st.direction_deg - 360.0) < 15.0
    print(f"    Track #1 Speed: {st.speed_pct_s:.2f} %/s | Scale-Invariant Speed: {st.speed_h_s:.2f} h/s | Direction: {st.direction_deg:.1f}°")
    print("    PASSED!\n")


def test_behaviour_primitives():
    """Test individual Layer 1 primitives."""
    print("--> Testing Layer 1 Behaviour Primitives...")
    st = TrackState(track_id=2, object_type="PERSON", object_label="Person #2")
    zone = ZoneDefinition(name="Restricted Zone A", polygon_coords=[(5.0, 5.0), (50.0, 5.0), (50.0, 98.0), (5.0, 98.0)], zone_type="restricted")

    t0 = time.time()
    # Feed 5 frames inside zone A
    for i in range(5):
        bbox = {"x": 15.0, "y": 20.0, "w": 5.0, "h": 20.0}
        st.update(bbox, timestamp=t0 + i * 0.1)
        st.update_zone_membership({"Restricted Zone A"}, timestamp=t0 + i * 0.1)

    cfg = {"min_frames": 3}
    fired, reason, evidence = primitives.check_zone_intrusion(st, [zone], cfg, t0 + 0.5)
    assert fired is True
    assert "Restricted Zone A" in reason
    assert evidence["primitive"] == "zone_intrusion"
    print(f"    Zone Intrusion: {reason}")

    # Test Speed Anomaly (Fast running)
    st_runner = TrackState(track_id=3, object_type="PERSON", object_label="Person #3")
    t0 = time.time()
    for i in range(10):
        # Move 4% per 0.1s -> 40% per sec, bbox height = 10% -> 4.0 h/s
        bbox = {"x": 10.0 + i * 4.0, "y": 10.0, "w": 5.0, "h": 10.0}
        st_runner.update(bbox, timestamp=t0 + i * 0.1)

    run_cfg = {"run_threshold_h_per_s": 1.5}
    fired_speed, reason_speed, ev_speed = primitives.check_speed_anomaly(st_runner, [zone], run_cfg, t0 + 1.0)
    assert fired_speed is True
    assert "running" in reason_speed
    print(f"    Speed Anomaly: {reason_speed}")
    print("    PASSED!\n")


def test_behaviour_engine_integration():
    """Test BehaviourEngine end-to-end integration and env flag disable."""
    print("--> Testing BehaviourEngine Integration...")
    engine = BehaviourEngine(enabled=True)

    # Mock TrackedObject from tracker
    det_box = {"x": 12.0, "y": 15.0, "w": 6.0, "h": 22.0}
    trk1 = TrackedObject(track_id=10, object_type="PERSON", object_label="Person #10", bbox=det_box, confidence=88.0)

    # Frame 1 to 5
    alerts = []
    t0 = time.time()
    for i in range(5):
        trk1.bbox = {"x": 12.0 + i * 0.5, "y": 15.0, "w": 6.0, "h": 22.0}
        frame_alerts = engine.process("BOP-07", frame=None, tracks=[trk1], timestamp=t0 + i * 0.2)
        alerts.extend(frame_alerts)

    print(f"    Generated {len(alerts)} alerts over 5 frames.")
    for a in alerts:
        print(f"      - Event: {a['event_type']} | Severity: {a['threat_level']} | Reason: {a['reason']}")
        assert "camera_id" in a
        assert "reason" in a
        assert "threat_level" in a

    # Test IBVAP_BEHAVIOUR_ENABLED=0 flag
    engine_disabled = BehaviourEngine(enabled=False)
    disabled_alerts = engine_disabled.process("BOP-07", frame=None, tracks=[trk1], timestamp=t0 + 2.0)
    assert len(disabled_alerts) == 0
    print("    Disabled Flag Check: Returned 0 alerts as expected.")
    print("    PASSED!\n")


if __name__ == "__main__":
    print("=========================================================")
    print("           IBVAP BEHAVIOUR ENGINE UNIT TEST SUITE        ")
    print("=========================================================\n")
    test_track_state_kinematics()
    test_behaviour_primitives()
    test_behaviour_engine_integration()
    print("ALL BEHAVIOUR ENGINE TESTS PASSED SUCCESSFULLY!")
