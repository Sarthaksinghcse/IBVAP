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
import threading
import requests
import numpy as np
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
from ai_engine.intelligence.face_engine import get_face_engine
from ai_engine.intelligence.face_config import MATCH_THRESHOLD_STRICT, MIN_FACE_PX
from ai_engine.preprocessing.frame_enhancer import FrameEnhancer

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pipeline")


class WatchlistSync:
    """
    Phase 2.1: Watchlist Sync Helper.
    Polls the backend for watchlist version changes and updates local embedding templates.
    """
    def __init__(self, backend_url: str):
        self.backend_url = backend_url
        self.records = []
        self.version = -1
        self._lock = threading.Lock()
        self._running = True

        # Initial sync
        self._sync()

        # Background poller
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _sync(self):
        try:
            r = requests.get(f"{self.backend_url}/api/watchlist/version", timeout=5)
            if r.status_code == 200:
                ver = r.json().get("version", -1)
                if ver > self.version:
                    r2 = requests.get(f"{self.backend_url}/api/watchlist/embeddings", timeout=10)
                    if r2.status_code == 200:
                        data = r2.json()
                        with self._lock:
                            self.records = [
                                {
                                    "person_id": rec["person_id"],
                                    "name": rec["name"],
                                    "identifier": rec.get("identifier"),
                                    "threat_priority": rec.get("threat_priority", "HIGH"),
                                    "embedding": np.array(rec["embedding"], dtype=np.float32)
                                }
                                for rec in data.get("records", [])
                            ]
                            self.version = data.get("version", ver)
                        logger.info(f"[WatchlistSync] Synced version {self.version} with {len(self.records)} records.")
        except Exception as e:
            logger.warning(f"[WatchlistSync] Sync failed (backend unreachable?): {e}")

    def _poll(self):
        while self._running:
            time.sleep(15.0)
            self._sync()

    def get_records(self):
        with self._lock:
            return self.records


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
        self.enhancer = FrameEnhancer()
        self.detector = Detector(model_path=model_path, conf_threshold=conf_threshold)
        self.tracker = Tracker()
        self.threat_engine = ThreatEngine(
            camera_id=camera_id,
            backend_url=backend_url,
            loitering_threshold=loitering_threshold
        )

        # Phase 2.2: Live face recognition against the watchlist
        self.face_eval_interval_frames = 5
        self.watchlist = WatchlistSync(backend_url)
        self.face_engine = get_face_engine()

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

                raw_frame = frame
                frame_for_inference, was_enhanced, enh_meta = self.enhancer.enhance(raw_frame)

                # 1. Run YOLOv8 Detection & Tracking on inference frame
                detections = self.detector.detect(frame_for_inference, camera_id=self.camera_id, track=True)

                # 2. Update Persistent Track Objects
                active_tracks = self.tracker.update(detections)

                # 2b. Live face recognition against the watchlist.
                # Recognition runs on the enhanced inference frame (so low-light footage benefits
                # from the enhancer); evidence snapshots still use the untouched raw frame.
                face_ms = 0.0
                watchlist_records = self.watchlist.get_records()

                if watchlist_records:
                    face_start = time.time()
                    for track in active_tracks:
                        if track.object_type != "PERSON":
                            continue

                        # Early out on tracks too small to yield a usable face crop
                        if track.bbox.get("h", 0) < (MIN_FACE_PX / 0.15):
                            continue

                        # Budget the cost: stagger evaluation across frames by track id
                        if (frame_idx % self.face_eval_interval_frames) != (track.track_id % self.face_eval_interval_frames):
                            continue

                        result = self.face_engine.evaluate_person_track_face(
                            frame_bgr=frame_for_inference,
                            person_bbox=track.bbox,
                            camera_id=self.camera_id,
                            track_id=track.track_id,
                            watchlist_records=watchlist_records,
                            threshold=MATCH_THRESHOLD_STRICT
                        )

                        if result.get("is_match") and result.get("consensus_state") == "CONFIRMED":
                            self.threat_engine.trigger_watchlist_alert(
                                person_id=result["person_id"],
                                person_name=result["person_name"],
                                identifier=result.get("identifier"),
                                threat_priority=result.get("threat_priority", "HIGH"),
                                similarity=result["similarity"],
                                cosine_score=result["cosine_score"],
                                track_id=track.track_id,
                                bbox=track.bbox,
                                is_in_zone=track.in_zone,
                                video_id=self.video_id
                            )

                    face_ms = (time.time() - face_start) * 1000

                # 3. Threat Engine Analysis & Event Dispatching (raw_frame preserved for snapshots/evidence)
                processed_dets = self.threat_engine.process_tracks(
                    active_tracks,
                    video_id=self.video_id,
                    frame_bgr=raw_frame,
                    inference_bgr=frame_for_inference
                )

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
                        f"[LOW_LIGHT] brightness={enh_meta['brightness']} enhancement={was_enhanced} | "
                        f"FPS: {curr_fps:.1f} | Detections: [{summary_str}] | "
                        f"Active Tracks: {len(active_tracks)} | Zone A: {zone_count} | Face ms: {face_ms:.1f}"
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
            try:
                self.face_engine.clear_cache()
            except Exception as fe:
                logger.warning(f"[Pipeline] Face engine scope cleanup failed: {fe}")
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
