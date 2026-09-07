import requests
import time

def test_upload_flow():
    video_path = r"E:\IBVAP\storage\videos\test_border.mp4"
    print("1. Uploading test video to FastAPI...")
    with open(video_path, "rb") as f:
        files = {"file": ("test_border_verification.mp4", f, "video/mp4")}
        r = requests.post("http://127.0.0.1:8000/api/videos/upload", files=files, data={"camera_id": "BOP-07"})

    print("Upload Response Code:", r.status_code)
    res = r.json()
    video_id = res["id"]
    print("Assigned Video ID:", video_id)
    print("Initial Status:", res.get("status"))

    print("\n2. Polling status while YOLOv8 processes...")
    for i in range(60):
        time.sleep(1.0)
        v = requests.get(f"http://127.0.0.1:8000/api/videos/{video_id}").json()
        curr_status = v.get("status")
        print(f"  T+{i+1}s: Status = {curr_status}")
        if curr_status in ["COMPLETED", "ERROR"]:
            break

    print("\n3. Querying stored detections for this specific video...")
    dets = requests.get(f"http://127.0.0.1:8000/api/detections/?video_id={video_id}&limit=500").json()
    print(f"Total Stored Detections: {len(dets)}")
    for d in dets[:5]:
        print(f" - [{d['event_type']}] {d['object_id']} ({d['confidence']}%) BBox: {d['bbox']}")

    print("\n4. Querying alerts generated...")
    alerts = requests.get("http://127.0.0.1:8000/api/alerts/?limit=5").json()
    print(f"Total Alerts in System: {len(alerts)}")

    if len(dets) > 0 and curr_status == "COMPLETED":
        print("\n>>> UPLOADED VIDEO TO REAL YOLOv8 WORKFLOW VERIFIED 100% <<<")
    else:
        print("\n>>> VERIFICATION FAILED <<<")

if __name__ == "__main__":
    test_upload_flow()
