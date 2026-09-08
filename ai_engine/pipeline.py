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

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pipeline")


class VideoStream:
    """Background thread to continuously grab frames, eliminating all buffer lag."""
    def __init__(self, src=0):
        if sys.platform == "win32" and isinstance(src, int):
            self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        else:
            self.cap = cv2.VideoCapture(src)
            
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video source: {src}")
            
        self.ret, self.frame = self.cap.read()
        self.stopped = False
        self.thread = threading.Thread(target=self.update, args=(), daemon=True)
        self.thread.start()

    def update(self):
        while not self.stopped:
            ret, frame = self.cap.read()
            if ret:
                self.ret = ret
                self.frame = frame

    def read(self):
        # Return a copy to prevent race conditions with the background thread
        return self.ret, self.frame.copy() if self.frame is not None else None

    def release(self):
        self.stopped = True
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.cap.release()

    def get(self, prop):
        return self.cap.get(prop)

    def set(self, prop, value):
        self.cap.set(prop, value)


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
        model_path: Optional[str] = None,
        throttle_fps: Optional[float] = 30.0,
        loop_video: bool = False,
        show_video: bool = True
    ):
        self.camera_id = camera_id
        self.source = source
        self.backend_url = backend_url
        self.video_id = video_id
        self.throttle_fps = throttle_fps
        self.loop_video = loop_video
        self.show_video = show_video
        
        # Phase 2.3: budget the cost
        self.face_eval_interval_frames = 5

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
        
        self.watchlist = WatchlistSync(backend_url)
        self.face_engine = get_face_engine()

    def _open_capture(self):
        """Open video file or threaded camera stream."""
        if isinstance(self.source, str) and self.source.isdigit():
            src = int(self.source)
            self.is_live = True
            return VideoStream(src)
        else:
            src = self.source
            self.is_live = False
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

                if not ret or frame is None:
                    if self.loop_video and not self.is_live:
                        logger.info("[Pipeline] Video loop reached end. Restarting stream...")
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    else:
                        logger.info("[Pipeline] Reached end of video file.")
                        break

                # Guarantee frame is a manageable size even if webcam ignored CAP_PROP
                h, w = frame.shape[:2]
                if w > 640 or h > 480:
                    frame = cv2.resize(frame, (640, int(640 * h / w)))

                frame_idx += 1
                processed_count += 1
                now_wall = time.time()

                # 1. Run YOLOv8 Detection & Tracking
                detections = self.detector.detect(frame, camera_id=self.camera_id, track=True)

                # 2. Update Persistent Track Objects
                active_tracks = self.tracker.update(detections, current_time=now_wall)

                # Phase 2.2: Live face recognition
                face_ms = 0.0
                face_eval_count = 0
                watchlist_records = self.watchlist.get_records()

                if watchlist_records:
                    face_start = time.time()
                    for track in active_tracks:
                        if track.object_type != "PERSON":
                            continue
                        
                        # Phase 2.3: Early out on small tracks
                        if track.bbox.get("h", 0) < (MIN_FACE_PX / 0.15):
                            continue
                            
                        # Budget the cost: evaluate each track periodically based on ID to distribute load
                        if (frame_idx % self.face_eval_interval_frames) != (track.track_id % self.face_eval_interval_frames):
                            continue
                        
                        face_eval_count += 1
                        result = self.face_engine.evaluate_person_track_face(
                            frame_bgr=frame, 
                            person_bbox=track.bbox, 
                            camera_id=self.camera_id, 
                            track_id=track.track_id,
                            watchlist_records=watchlist_records, 
                            now=now_wall, 
                            threshold=MATCH_THRESHOLD_STRICT
                        )
                        
                        if result.get("is_match") and result.get("consensus_state") == "CONFIRMED":
                            # Post alert directly through ThreatEngine to backend API
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
                                frame_bgr=frame
                            )
                    
                    face_ms = (time.time() - face_start) * 1000

                # 3. Threat Engine Analysis & Event Dispatching (Zone Intrusion & Dwell)
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
                        f"Active Tracks: {len(active_tracks)}/{len(self.tracker.tracks)} | Zone A: {zone_count} | Face ms: {face_ms:.1f}"
                    )

                # Visual Display
                if self.show_video:
                    # Draw tracking boxes with behaviour labels for visual feedback
                    display_frame = frame.copy()
                    for track in active_tracks:
                        h_f, w_f = display_frame.shape[:2]
                        x1 = int((track.bbox["x"] / 100.0) * w_f)
                        y1 = int((track.bbox["y"] / 100.0) * h_f)
                        w_b = int((track.bbox["w"] / 100.0) * w_f)
                        h_b = int((track.bbox["h"] / 100.0) * h_f)

                        # Get behaviour label for this track from the threat engine's behaviour engine
                        b_label, _ = self.threat_engine.behaviour_engine.classify(track.track_id)
                        b_str = b_label.value if hasattr(b_label, "value") else str(b_label)

                        # Color code: green=normal, yellow=attention, red=high threat
                        if b_str in ("RUNNING", "CIRCLING"):
                            box_color = (0, 0, 255)       # Red
                        elif b_str in ("PACING", "ERRATIC_MOVEMENT", "STATIONARY"):
                            box_color = (0, 200, 255)     # Yellow/Orange
                        else:
                            box_color = (0, 255, 0)       # Green

                        cv2.rectangle(display_frame, (x1, y1), (x1 + w_b, y1 + h_b), box_color, 2)

                        # Draw trajectory breadcrumbs
                        if hasattr(track, 'trajectory') and len(track.trajectory) > 1:
                            t_pts = [
                                (int((pt[0] / 100.0) * w_f), int((pt[1] / 100.0) * h_f))
                                for pt in track.trajectory
                            ]
                            for i in range(1, len(t_pts)):
                                cv2.line(display_frame, t_pts[i - 1], t_pts[i], box_color, 2)
                            cv2.circle(display_frame, t_pts[-1], 4, (0, 255, 255), -1)

                        # Show label with behaviour tag
                        display_label = f"{track.object_label}"
                        if b_str != "NORMAL_TRANSIT":
                            display_label += f" [{b_str}]"
                        cv2.putText(display_frame, display_label, (x1, max(0, y1 - 10)), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, box_color, 2)
                        
                    cv2.imshow("IBVAP Live Camera Feed", display_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        logger.info("[Pipeline] 'q' pressed, exiting.")
                        break

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
            self.face_engine.clear_scope("live") # Clear live scope on exit
            logger.info(f"[Pipeline] Processing Complete. Processed {processed_count} frames in {total_time:.2f}s ({processed_count/total_time:.1f} avg FPS).")


def main():
    parser = argparse.ArgumentParser(description="IBVAP Real YOLOv8 AI Pipeline")
    parser.add_argument("--camera",    default="BOP-07",                      help="Border Camera ID (e.g. BOP-07)")
    parser.add_argument("--source",    default="0",                           help="Path to MP4 or RTSP stream, or webcam index")
    parser.add_argument("--backend",   default="http://localhost:8000",         help="FastAPI Backend URL")
    parser.add_argument("--video-id",  default=None,                          help="Optional Video ID in DB")
    parser.add_argument("--conf",      type=float, default=0.40,             help="Detection confidence threshold (0.0 - 1.0)")
    parser.add_argument("--loiter",    type=float, default=15.0,             help="Loitering threshold in seconds")
    parser.add_argument("--model",     default=None,                          help="Path to YOLOv8n model weights (auto-discovered if omitted)")
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
