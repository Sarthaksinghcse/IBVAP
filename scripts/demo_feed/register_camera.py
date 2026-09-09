"""
Stage 3 of the demo feed builder — register the rendered clip as a camera.

The rendered MP4 is served through the normal camera stream path, so it shows up
in the dashboard, the multi-camera grid and the MJPEG endpoint exactly like a
real feed. source_type is PLAYBACK, which tells CameraStreamWorker to pace the
file at its own frame rate, loop it seamlessly, and leave the AI loop off
(the overlays are already burnt in).

    python scripts/demo_feed/register_camera.py \
        --video storage/demo_feed/anomaly_demo_feed.mp4
"""
import os
import sys
import argparse

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
for p in (_REPO_ROOT, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

import cv2
from database.database import SessionLocal
from models.models import Camera


def register(video_path: str, cam_id: str, name: str, location: str) -> None:
    if not os.path.exists(video_path):
        raise SystemExit(f"Rendered video not found: {video_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise SystemExit(f"Could not open rendered video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    db = SessionLocal()
    try:
        cam = db.query(Camera).filter(Camera.id == cam_id).first()
        created = cam is None
        if created:
            cam = Camera(id=cam_id)
            db.add(cam)

        cam.name = name
        cam.location = location
        cam.source_type = "PLAYBACK"
        cam.stream_url = video_path.replace("\\", "/")
        cam.stream_type = "MJPEG"
        cam.status = "ONLINE"
        cam.ai_status = "STOPPED"     # overlays are pre-rendered, not live
        cam.fps = round(float(fps), 2)
        cam.resolution = f"{w}x{h}"
        cam.rotation = 0

        db.commit()
        print(f"[register] {'created' if created else 'updated'} camera {cam_id}")
        print(f"[register]   name       {cam.name}")
        print(f"[register]   source     {cam.stream_url}")
        print(f"[register]   {cam.resolution} @ {cam.fps} fps")
        print(f"[register]   stream     GET /api/cameras/{cam_id}/stream")
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(description="Register the rendered demo clip as a playback camera.")
    p.add_argument("--video", required=True)
    p.add_argument("--id", default="CAM-DEMO-ANOM")
    p.add_argument("--name", default="Hall Perimeter (Behaviour Demo)")
    p.add_argument("--location", default="Main Hall — North Corridor")
    a = p.parse_args()

    video = a.video if os.path.isabs(a.video) else os.path.join(_REPO_ROOT, a.video)
    register(os.path.abspath(video), a.id, a.name, a.location)


if __name__ == "__main__":
    main()
