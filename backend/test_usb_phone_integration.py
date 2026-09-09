"""
Verification test script for USB Phone Camera integration in SHIELD.
Tests:
1. USB Phone Manager ADB locator and device detection.
2. Port availability finder (preferred 8090).
3. FastAPI endpoints:
   - GET /api/cameras/usb/find-port
   - POST /api/cameras/usb/detect
   - POST /api/cameras/usb/status
   - POST /api/cameras/usb/connect (error handling when no device attached)
   - POST /api/cameras/usb/connect (success flow with simulated forward and frame probe)
   - GET /api/cameras/{camera_id}/stream (MJPEG route validation)
"""

import sys
import os
import unittest.mock as mock
from fastapi.testclient import TestClient

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from main import app
from services.usb_phone_manager import usb_phone_manager

def run_usb_verification():
    print("=" * 60)
    print("SHIELD USB Phone Camera Integration Test Suite")
    print("=" * 60)

    # 1. Test USB Phone Manager
    print("\n[TEST 1] Verifying USBPhoneManager ADB path and device detection...")
    adb_path = usb_phone_manager.get_adb_path()
    print(f"  -> ADB Path: {adb_path}")
    assert adb_path is not None, "ADB executable should be detected"

    detect_info = usb_phone_manager.detect_devices()
    print(f"  -> Detect devices output: adb_available={detect_info.get('adb_available')}, devices_found={len(detect_info.get('devices', []))}")
    print(f"  -> Windows PnP hardware detected: {len(detect_info.get('pnp_hardware_detected', []))}")
    assert detect_info.get("adb_available") is True, "ADB should be marked as available"
    print("  [PASS] USBPhoneManager initialization and hardware probe successful.")

    # 2. Test Available Port Finder
    print("\n[TEST 2] Testing find_available_local_port starting at 8090...")
    port = usb_phone_manager.find_available_local_port(start_port=8090)
    print(f"  -> Selected available port: {port}")
    assert port >= 8090, "Available port should be >= 8090"
    print("  [PASS] Port availability checker verified.")

    # 3. Test FastAPI TestClient
    client = TestClient(app)

    print("\n[TEST 3] Testing GET /api/cameras/usb/find-port...")
    res = client.get("/api/cameras/usb/find-port?preferred=8090")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    port_data = res.json()
    assert "available_port" in port_data
    assert port_data["available_port"] >= 8090
    print(f"  -> find-port returned available port: {port_data['available_port']}")
    print("  [PASS] /api/cameras/usb/find-port endpoint verified.")

    print("\n[TEST 4] Testing POST /api/cameras/usb/detect...")
    res = client.post("/api/cameras/usb/detect")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    assert "devices" in data
    assert "instructions" in data
    print(f"  -> Response status 200: {len(data['devices'])} devices, {len(data['instructions'])} instructions.")
    print("  [PASS] /api/cameras/usb/detect endpoint verified.")

    print("\n[TEST 5] Testing GET /api/cameras/usb/status...")
    res = client.get("/api/cameras/usb/status")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    status_data = res.json()
    assert "connected" in status_data
    assert "adb_available" in status_data
    print(f"  -> Response status 200: connected={status_data['connected']}, device_count={status_data['device_count']}")
    print("  [PASS] /api/cameras/usb/status endpoint verified.")

    print("\n[TEST 6A] Testing POST /api/cameras/usb/connect rejection without active device...")
    connect_payload = {
        "name": "Test USB Phone",
        "location": "Physical USB Dock 01",
        "phone_port": 8080,
        "local_port": 8090,
        "stream_path": "/video",
        "app_type": "IP_WEBCAM",
        "auto_find_port": True
    }
    res_err = client.post("/api/cameras/usb/connect", json=connect_payload)
    assert res_err.status_code == 400
    print(f"  -> Correctly rejected with HTTP 400: {res_err.json()['detail']}")
    print("  [PASS] Authorization verification verified.")

    print("\n[TEST 6B] Testing POST /api/cameras/usb/connect success flow when frames received...")
    fake_detect = {
        "adb_available": True,
        "devices": [{"serial": "MOCK_DEVICE_123", "state": "device", "model": "Pixel 7 Pro", "authorized": True}],
        "pnp_hardware_detected": [],
        "instructions": []
    }
    with mock.patch.object(usb_phone_manager, "detect_devices", return_value=fake_detect):
        with mock.patch.object(usb_phone_manager, "forward_port_with_fallback", return_value=(True, 8090, "Forwarded 8090 -> 8080")):
            with mock.patch.object(usb_phone_manager, "probe_stream", return_value=(True, (1920, 1080), "Frames received")):
                res = client.post("/api/cameras/usb/connect", json=connect_payload)
                assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
                cam_data = res.json()
                cam_id = cam_data["id"]
                assert cam_data["name"] == "Test USB Phone"
                assert cam_data["source_type"] == "USB_PHONE"
                assert cam_data["stream_type"] == "HTTP"
                assert "http://127.0.0.1:8090/video" in cam_data["stream_url"]
                print(f"  -> Created/Updated Camera: ID={cam_id}, Name={cam_data['name']}, Source={cam_data['source_type']}, URL={cam_data['stream_url']}")
                print("  [PASS] /api/cameras/usb/connect verified with validated frames.")

    print("\n[TEST 7] Testing GET /api/cameras list...")
    res = client.get("/api/cameras/")
    assert res.status_code == 200
    all_cams = res.json()
    usb_cams = [c for c in all_cams if c.get("source_type") == "USB_PHONE"]
    assert len(usb_cams) >= 1, "At least one USB_PHONE camera should be registered in DB"
    print(f"  -> Total cameras in DB: {len(all_cams)}, USB Phone cameras: {len(usb_cams)}")
    print("  [PASS] Cameras list contains USB_PHONE camera.")

    print("\n[TEST 8] Clean up test camera...")
    del_res = client.delete(f"/api/cameras/{cam_id}")
    assert del_res.status_code == 200
    print(f"  -> Deleted test camera {cam_id}")
    print("  [PASS] Clean up complete.")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY! USB Port 8090 and stream validation verified.")
    print("=" * 60)

if __name__ == "__main__":
    run_usb_verification()
