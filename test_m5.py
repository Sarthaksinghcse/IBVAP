import cv2
import numpy as np
import os
from pathlib import Path
from ai_engine.intelligence.threat_engine import ThreatEngine
from ai_engine.tracking.tracker import TrackedObject

def test_snapshot():
    print("Testing M5: Snapshot Auto-Capture")
    
    # 1. Create a dummy ThreatEngine with a mock callback
    captured_payloads = []
    def mock_alert_callback(payload):
        captured_payloads.append(payload)

    engine = ThreatEngine(camera_id="TEST-01", alert_callback=mock_alert_callback, restricted_zone_polygon=[(5.0, 5.0), (50.0, 5.0), (50.0, 98.0), (5.0, 98.0)])
    engine.min_confidence = 0.5 # 50%
    engine.alert_cooldown = 0
    
    # 2. Create a dummy frame (480x640 blue image)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (255, 0, 0)
    
    # 3. Create a tracked object inside a zone
    # Restricted Zone A default: (5,5) to (50,98)
    track = TrackedObject(
        track_id=1,
        object_type="PERSON",
        object_label="Person",
        confidence=95.0,
        bbox={"x": 20.0, "y": 20.0, "w": 10.0, "h": 20.0}
    )
    track.in_zone = True
    
    # 4. Trigger process_tracks to simulate loitering for 30+ seconds (default threshold is 30)
    # We will just forcefully set loiter time to 35
    import time
    track.update_zone_status(True, engine.zone_name)
    track.zone_entry_time = time.time() - 35
    
    # Process tracks
    results = engine.process_tracks([track], frame_bgr=frame)
    print(f"Process tracks returned: {results}")
    
    # 5. Check if callback received the alert with snapshot
    if not captured_payloads:
        print("FAILED: No alert was triggered.")
        return
        
    payload = captured_payloads[0]
    print(f"Alert triggered: {payload['threat_level']}")
    snapshot_path = payload.get("snapshot_path")
    
    if not snapshot_path:
        print("FAILED: Alert payload missing snapshot_path.")
        return
        
    print(f"Snapshot path returned: {snapshot_path}")
    
    # 6. Verify file exists
    full_path = Path.cwd() / snapshot_path
    if not full_path.exists():
        print(f"FAILED: Snapshot file not found at {full_path}")
        return
        
    # Verify file is not empty
    if full_path.stat().st_size == 0:
        print(f"FAILED: Snapshot file is empty.")
        return
        
    print("SUCCESS: Snapshot captured, saved, and attached to alert payload correctly.")
    
    # Optional: Test watchlist alert too
    print("\nTesting Watchlist Snapshot...")
    captured_payloads.clear()
    
    engine.trigger_watchlist_alert(
        person_id="TEST_PERSON",
        person_name="John Doe",
        identifier="EMP123",
        threat_priority="CRITICAL",
        similarity=98.5,
        cosine_score=0.98,
        track_id=2,
        bbox={"x": 30.0, "y": 30.0, "w": 15.0, "h": 25.0},
        is_in_zone=False,
        frame_bgr=frame
    )
    
    if not captured_payloads:
        print("FAILED: Watchlist alert not triggered.")
        return
        
    wl_payload = captured_payloads[0]
    wl_snapshot = wl_payload.get("snapshot_path")
    
    if not wl_snapshot:
        print("FAILED: Watchlist payload missing snapshot_path.")
        return
        
    wl_full_path = Path.cwd() / wl_snapshot
    if not wl_full_path.exists():
        print(f"FAILED: Watchlist snapshot file not found at {wl_full_path}")
        return
        
    print("SUCCESS: Watchlist snapshot captured, saved, and attached correctly.")
    
if __name__ == "__main__":
    test_snapshot()
