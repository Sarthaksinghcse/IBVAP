import os
import cv2
import time
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

logger = logging.getLogger("ibvap")

router = APIRouter()

def generate_demo_frames():
    """
    Generator function for MJPEG streaming of anomalous_hall.mp4 with real-time HUD rendering.
    """
    video_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "storage", "videos", "anomalous_hall.mp4")
    )
    if not os.path.exists(video_path):
        logger.error(f"[Stream] Demo video not found at {video_path}")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"[Stream] Failed to open {video_path}")
        return

    try:
        from ai_engine.intelligence.behaviour_engine import BehaviourEngine
        behaviour_engine = BehaviourEngine()
    except Exception as e:
        logger.warning(f"[Stream] Could not initialize BehaviourEngine: {e}")
        behaviour_engine = None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_delay = 1.0 / fps

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            # Loop the video continuously
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        # Draw HUD on top left
        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"CAM-01 LIVE | {timestamp_str}", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

        # Encode frame as JPEG
        ret_img, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret_img:
            continue

        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

        time.sleep(frame_delay)

@router.get("/demo")
def get_demo_stream():
    return StreamingResponse(
        generate_demo_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
