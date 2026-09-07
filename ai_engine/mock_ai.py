"""
IBVAP Mock AI Engine
====================
Simulates the YOLO + DeepSORT detection pipeline for development/demo.

Usage:
    python ai_engine/mock_ai.py

This script sends realistic detection + alert events to the FastAPI backend
through the same API endpoints that the real YOLO AI engine will use.

This means the Web Portal and Security Software see IDENTICAL event flows
whether this mock script or the real YOLO engine is running.

To switch to real AI: just replace this script with the real YOLO pipeline.
"""
import time
import random
import uuid
import requests
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [MockAI] %(message)s")
logger = logging.getLogger("mock_ai")

# ─── Config ───────────────────────────────────────────────────────────────────

BASE_URL   = "http://localhost:8000"
CAMERAS    = ["BOP-01", "BOP-02", "BOP-03", "BOP-05", "BOP-07"]
EVENT_DELAY = (6, 18)   # seconds between events (min, max)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def rand(lo, hi): return random.randint(lo, hi)
def randf(lo, hi): return round(random.uniform(lo, hi), 2)
def pick(lst): return random.choice(lst)
def uid(): return str(uuid.uuid4())[:8].upper()


def post(endpoint: str, data: dict) -> dict | None:
    try:
        r = requests.post(f"{BASE_URL}{endpoint}", json=data, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        logger.error(f"Backend not reachable at {BASE_URL}. Is the backend running?")
        return None
    except Exception as e:
        logger.error(f"POST {endpoint} failed: {e}")
        return None


# ─── Detection Generators ────────────────────────────────────────────────────

def make_person_detection(camera_id: str) -> dict:
    in_zone   = random.random() < 0.25
    loitering = in_zone and random.random() < 0.5
    return {
        "camera_id":             camera_id,
        "object_type":           "PERSON",
        "object_id":             f"Person #{rand(1, 25):02d}",
        "confidence":            randf(82, 99),
        "zone":                  "Restricted Zone A" if in_zone else None,
        "event_type":            "ZONE_INTRUSION" if in_zone else ("LOITERING" if loitering else "PERSON_DETECTED"),
        "bbox":                  {"x": randf(5, 75), "y": randf(10, 50), "w": randf(8, 16), "h": randf(30, 55)},
        "is_in_restricted_zone": in_zone,
        "loitering_duration":    rand(15, 90) if loitering else None,
        "timestamp":             datetime.utcnow().isoformat(),
    }


def make_vehicle_detection(camera_id: str) -> dict:
    return {
        "camera_id":             camera_id,
        "object_type":           "VEHICLE",
        "object_id":             f"Vehicle #{rand(1, 10):02d}",
        "confidence":            randf(88, 98),
        "event_type":            "VEHICLE_DETECTED",
        "bbox":                  {"x": randf(10, 60), "y": randf(45, 65), "w": randf(20, 35), "h": randf(15, 28)},
        "is_in_restricted_zone": False,
        "timestamp":             datetime.utcnow().isoformat(),
    }


# ─── Alert Generators ─────────────────────────────────────────────────────────

def should_generate_alert(det: dict) -> bool:
    event = det["event_type"]
    return event in ("ZONE_INTRUSION", "LOITERING") or \
           (det["object_type"] == "VEHICLE" and random.random() < 0.4)


def threat_level_for(det: dict) -> str:
    event = det["event_type"]
    if event == "ZONE_INTRUSION":
        dur = det.get("loitering_duration") or 0
        return "CRITICAL" if dur > 25 else "HIGH"
    if event == "LOITERING":
        return "HIGH"
    if det["object_type"] == "VEHICLE":
        return "MEDIUM"
    return "LOW"


def make_alert(det: dict) -> dict:
    event     = det["event_type"]
    obj_id    = det["object_id"]
    zone      = det.get("zone") or "monitored zone"
    dur       = det.get("loitering_duration") or 0

    reasons = {
        "ZONE_INTRUSION":   f"{obj_id} entered {zone} and stayed for {dur}s. Confidence: {det['confidence']}%.",
        "LOITERING":        f"{obj_id} detected loitering near perimeter for {dur}s.",
        "VEHICLE_DETECTED": f"Unidentified vehicle ({obj_id}) detected in monitored area.",
        "PERSON_DETECTED":  f"{obj_id} detected in monitored zone. Confidence: {det['confidence']}%.",
    }

    return {
        "camera_id":    det["camera_id"],
        "event_type":   event,
        "object_type":  det["object_type"],
        "object_id":    obj_id,
        "threat_level": threat_level_for(det),
        "reason":       reasons.get(event, f"{event} detected by AI engine."),
    }


# ─── Main Loop ────────────────────────────────────────────────────────────────

def run():
    logger.info("Mock AI Engine started.")
    logger.info(f"Targeting backend: {BASE_URL}")
    logger.info("Press Ctrl+C to stop.\n")

    while True:
        camera_id = pick(CAMERAS)
        is_vehicle = random.random() < 0.3

        # Generate detection
        det = make_vehicle_detection(camera_id) if is_vehicle else make_person_detection(camera_id)

        result = post("/api/detections", det)
        if result:
            logger.info(f"Detection: [{det['event_type']}] {det['object_id']} @ {camera_id} ({det['confidence']}%)")

        # Generate alert if notable event
        if result and should_generate_alert(det):
            time.sleep(0.5)
            alert = make_alert(det)
            a_result = post("/api/alerts", alert)
            if a_result:
                logger.info(f"  ⚠ Alert: [{alert['threat_level']}] {alert['event_type']} → {a_result.get('alert_id')}")

        # Wait between events
        delay = random.uniform(*EVENT_DELAY)
        logger.info(f"  Next event in {delay:.1f}s…")
        time.sleep(delay)


if __name__ == "__main__":
    run()
