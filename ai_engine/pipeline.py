"""
IBVAP AI Pipeline — Real YOLOv8 Surveillance Engine
===================================================
Orchestrates OpenCV video stream extraction, YOLOv8n inference,
object tracking, restricted-zone detection, loitering analysis,
and event dispatching to the FastAPI backend.
"""
import os
import sys
import time
import argparse
import logging
from typing import Optional

# Setup sys.path so modules can be run directly
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import cv2
from ai_engine.detection.detector import Detector
from ai_engine.tracking.tracker import Tracker
from ai_engine.intelligence.threat_engine import ThreatEngine

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pipeline")


class IBVAPPipeline:
    """
    Core AI Pipeline integrating YOLOv8n, Tracking, and Threat Assessment.
    """

    def __init__(
        self,
        camera_id: str = "BOP-07",
        source: str = "0",
        backend_url: str = "http://localhost:8000",
        video_id: Optional[str] = None,
        conf_threshold: float = 0.40,
        loitering_threshold: float = 15.0,  # 15s prototype threshold
        model_path: str = "E:/IBVAP/models/yolov8n.pt",
        throttle_fps: Optional[float] = 30.0,
        loop_video: bool = False
    ):
        self.camera_id = camera_id
        self.source = source
        self.backend_url = backend_url
        self.video_id = video_id
        self.throttle_fps = throttle_fps
        self.loop_video = loop_video

        logger.info(f"╔════════════════════════════════════════════════════════════════╗")
        logger.info(f"║             IBVAP REAL YOLOv8n SURVEILLANCE ENGINE             ║")
        logger.info(f"╠════════════════════════════════════════════════════════════════╣")
        logger.info(f"║  Camera ID:      {self.camera_id:<46}║")
        logger.info(f"║  Source:         {str(self.source):<46}║")
        logger.info(f"║  Backend Hub:    {self.backend_url:<46}║")
        logger.info(f"║  Loiter Limit:   {str(loitering_threshold) + 's':<46}║")
        logger.info(f"╚════════════════════════════════════════════════════════════════╝")

        # Initialize Subsystems
        self.detector = Detector(model_path=model_path, conf_threshold=conf_threshold)
        self.tracker = Tracker()
        self.threat_engine = ThreatEngine(
            camera_id=camera_id,
            backend_url=backend_url,
            loitering_threshold=loitering_threshold
        )

    def _open_capture(self) -> cv2.VideoCapture:
        """Open video file or camera stream."""
        # Convert integer string index for webcam if applicable
        if isinstance(self.source, str) and self.source.isdigit():
            src = int(self.source)
        else:
            src = self.source

        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            raise RuntimeError(f"[Pipeline] Could not open video source: {self.source}")
        return cap

    def run(self):
        """Execute the video processing and analysis loop."""
        cap = self._open_capture()
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        native_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        logger.info(f"[Pipeline] Video Stream Opened: {width}x{height} @ {native_fps:.1f} FPS (Total Frames: {total_frames})")

        frame_idx = 0
        target_frame_delay = 1.0 / (self.throttle_fps or native_fps) if self.throttle_fps else 0.0
        start_time = time.time()
        processed_count = 0

        try:
            while True:
                loop_start = time.time()
                ret, frame = cap.read()

                if not ret:
                    if self.loop_video:
                        logger.info("[Pipeline] Video loop reached end. Restarting stream...")
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    else:
                        logger.info("[Pipeline] Reached end of video file.")
                        break

                frame_idx += 1
                processed_count += 1

                # 1. Run YOLOv8 Detection & Tracking
                detections = self.detector.detect(frame, camera_id=self.camera_id, track=True)

                # 2. Update Persistent Track Objects
                active_tracks = self.tracker.update(detections)

                # 3. Threat Engine Analysis & Event Dispatching
                processed_dets = self.threat_engine.process_tracks(active_tracks, video_id=self.video_id, frame_bgr=frame)

                # 4. Performance & Telemetry Reporting
                elapsed = time.time() - start_time
                curr_fps = processed_count / elapsed if elapsed > 0 else 0.0

                if frame_idx % 15 == 0 or len(detections) > 0:
                    counts_summary = {}
                    for d in detections:
                        counts_summary[d.object_type] = counts_summary.get(d.object_type, 0) + 1
                    summary_str = ", ".join([f"{k}: {v}" for k, v in counts_summary.items()]) or "No targets"
                    
                    zone_count = sum(1 for t in active_tracks if t.in_zone)
                    logger.info(
                        f"[Frame {frame_idx:04d}/{total_frames or 'Live'}] "
                        f"FPS: {curr_fps:.1f} | Detections: [{summary_str}] | "
                        f"Active Tracks: {len(active_tracks)} | Zone A: {zone_count}"
                    )

                # 5. Throttle loop if pacing is desired
                if target_frame_delay > 0:
                    process_time = time.time() - loop_start
                    delay = target_frame_delay - process_time
                    if delay > 0:
                        time.sleep(delay)

        except KeyboardInterrupt:
            logger.info("[Pipeline] Interrupted by user.")
        finally:
            cap.release()
            total_time = time.time() - start_time
            logger.info(f"[Pipeline] Processing Complete. Processed {processed_count} frames in {total_time:.2f}s ({processed_count/total_time:.1f} avg FPS).")


def main():
    parser = argparse.ArgumentParser(description="IBVAP Real YOLOv8 AI Pipeline")
    parser.add_argument("--camera",    default="BOP-07",                      help="Border Camera ID (e.g. BOP-07)")
    parser.add_argument("--source",    default="E:/IBVAP/storage/videos/test_border.mp4", help="Path to MP4 or RTSP stream")
    parser.add_argument("--backend",   default="http://localhost:8000",         help="FastAPI Backend URL")
    parser.add_argument("--video-id",  default=None,                          help="Optional Video ID in DB")
    parser.add_argument("--conf",      type=float, default=0.40,             help="Detection confidence threshold (0.0 - 1.0)")
    parser.add_argument("--loiter",    type=float, default=15.0,             help="Loitering threshold in seconds")
    parser.add_argument("--model",     default="E:/IBVAP/models/yolov8n.pt",  help="Path to YOLOv8n model weights")
    parser.add_argument("--fps",       type=float, default=30.0,             help="Frame rate processing limit (0 for unlimited)")
    parser.add_argument("--loop",      action="store_true",                   help="Loop video continuously")
    args = parser.parse_args()

    pipeline = IBVAPPipeline(
        camera_id=args.camera,
        source=args.source,
        backend_url=args.backend,
        video_id=args.video_id,
        conf_threshold=args.conf,
        loitering_threshold=args.loiter,
        model_path=args.model,
        throttle_fps=args.fps if args.fps > 0 else None,
        loop_video=args.loop
    )
    pipeline.run()


if __name__ == "__main__":
    main()
