"""
Low-Latency Camera Stream Worker & Decoupled AI Pipeline Service.
================================================================
Eliminates camera streaming latency over USB and RTSP via:
1. A high-speed reader thread that continuously drains the socket into a 1-frame atomic slot.
2. Immediate frame dropping for stale frames (latest-frame strategy).
3. A decoupled background AI thread running YOLOv8 + Tracker + ThreatEngine independently.
4. Smooth live MJPEG display generation that never freezes or waits for YOLO inference.
5. Real runtime metrics (Camera FPS, AI FPS, Latency ms) measured dynamically from runtime.
"""

import os
import sys
import cv2
import time
import uuid
import json
import logging
import threading
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# Ensure repository root is in sys.path for ai_engine imports
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from database.database import SessionLocal
from models.models import Camera, Zone, Alert, ANPREvent, WatchlistPlate, Detection as DB_Detection
from websocket.manager import manager
from routes.alerts import create_and_broadcast_alert_sync
from ai_engine.detection.detector import Detector, ALL_SUPPORTED_CLASSES
from ai_engine.tracking.tracker import Tracker, TrackedObject
from ai_engine.intelligence.threat_engine import ThreatEngine

logger = logging.getLogger("camera_worker")

# Shared detector singleton to save VRAM/RAM
_shared_detector: Optional[Detector] = None
_detector_lock = threading.Lock()

def get_shared_detector() -> Detector:
    global _shared_detector
    with _detector_lock:
        if _shared_detector is None:
            logger.info("[CameraWorker] Initializing shared YOLOv8n detector...")
            _shared_detector = Detector(conf_threshold=0.45)
        return _shared_detector


class CameraStreamWorker:
    """
    Dedicated worker for a live camera source (USB Phone or CCTV).
    Decouples frame capture from YOLOv8 inference to guarantee real-time low latency (<500ms).
    """

    def __init__(
        self,
        camera_id: str,
        stream_url: str,
        source_type: str = "USB_PHONE",
        conf_threshold: float = 0.30,
        rotation: int = 0
    ):
        self.camera_id = camera_id
        self.stream_url = stream_url
        self.source_type = source_type
        self.conf_threshold = conf_threshold
        self.rotation = int(rotation)  # 0, 90, 180, 270
        self.is_usb = (source_type == "USB_PHONE")
        self.session_id = f"SESS-{uuid.uuid4().hex[:8].upper()}"
        self.session_start_time = time.time()

        # Worker lifecycle
        self._stopped = False
        self._reader_thread: Optional[threading.Thread] = None
        self._ai_thread: Optional[threading.Thread] = None

        # Frame buffer (Latest-frame only)
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_time: float = 0.0
        self._frame_seq: int = 0
        self._dropped_frames_total: int = 0

        # AI tracking & detection state
        self._last_ai_frame_seq: int = -1
        self._latest_tracks: List[TrackedObject] = []
        self._latest_ai_timestamp: float = 0.0
        self._last_ai_infer_time_ms: float = 0.0

        # Measured runtime metrics
        self._measured_cam_fps: float = 0.0
        self._measured_ai_fps: float = 0.0
        self._measured_latency_ms: float = 0.0

        # Internal metric calculation accumulators
        self._cam_fps_count: int = 0
        self._cam_fps_window_start: float = time.time()
        self._ai_fps_count: int = 0
        self._ai_fps_window_start: float = time.time()

        # Viewers and activity tracking
        self._active_viewers: int = 0
        self._last_viewer_time: float = time.time()

        # Camera-specific AI pipelines (persistent tracker & threat engine)
        self.tracker = Tracker()
        self.threat_engine = ThreatEngine(
            camera_id=self.camera_id,
            loitering_threshold=15.0,
            alert_callback=create_and_broadcast_alert_sync,
            detection_callback=None
        )
        self.detector = get_shared_detector()

        # Deduplication state: track_id -> last_logged_time
        self._logged_tracks: Dict[int, float] = {}
        self._logged_states: Dict[int, str] = {}

        # Load zone configuration and camera orientation from database
        self.refresh_zone_from_db()

        # Start worker threads
        self.start()

    def start(self):
        """Start the ingestion reader thread and the decoupled AI thread."""
        self._stopped = False
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name=f"Reader-{self.camera_id}",
            daemon=True
        )
        self._ai_thread = threading.Thread(
            target=self._ai_loop,
            name=f"AI-{self.camera_id}",
            daemon=True
        )
        self._reader_thread.start()
        self._ai_thread.start()
        logger.info(f"[CameraWorker] Started stream worker for {self.camera_id} -> {self.stream_url} (rotation={self.rotation} deg)")

    def stop(self):
        """Gracefully stop worker threads and clear active live tracking state."""
        self._stopped = True
        self._latest_tracks = []
        with self._frame_lock:
            self._latest_frame = None
        logger.info(f"[CameraWorker] Stopping stream worker for {self.camera_id} (session {self.session_id} terminated)")

    def refresh_zone_from_db(self):
        """Load configured restricted zone and rotation for this camera from database."""
        db = SessionLocal()
        try:
            cam_rec = db.query(Camera).filter(Camera.id == self.camera_id).first()
            if cam_rec and cam_rec.rotation is not None:
                self.rotation = int(cam_rec.rotation)

            cam_zone = db.query(Zone).filter(Zone.source_id == self.camera_id, Zone.enabled == True).first()
            if cam_zone and cam_zone.coordinates_json:
                coords = json.loads(cam_zone.coordinates_json)
                self.threat_engine.set_zone(coords, cam_zone.name)
                logger.info(f"[CameraWorker] Loaded zone '{cam_zone.name}' for {self.camera_id}")
            else:
                self.threat_engine.set_zone(None, None)
        except Exception as e:
            logger.warning(f"[CameraWorker] Error loading zone/rotation for {self.camera_id}: {e}")
            self.threat_engine.set_zone(None, None)
        finally:
            db.close()

    def set_rotation(self, deg: int):
        """Set frame rotation in degrees (0, 90, 180, 270)."""
        valid_rotations = [0, 90, 180, 270]
        deg = deg % 360
        if deg in valid_rotations:
            self.rotation = deg
            logger.info(f"[CameraWorker] Camera {self.camera_id} rotation updated to {deg} deg")

    def set_confidence(self, conf: float):
        """Update confidence threshold dynamically."""
        if 0.05 <= conf <= 1.0:
            self.conf_threshold = conf
            logger.info(f"[CameraWorker] Updated confidence threshold for {self.camera_id} to {conf:.2f}")

    def _reader_loop(self):
        """
        Continuous ingestion thread.
        Reads frames as fast as they arrive over the socket, ensuring ZERO socket buffer buildup.
        Always keeps only the newest frame and drops older stale frames.
        """
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;2000000|rtsp_transport;tcp"
        cap = cv2.VideoCapture(self.stream_url)
        # Minimize internal buffering in OpenCV backend where supported
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        consecutive_failures = 0
        last_log_time = time.time()

        while not self._stopped:
            if not cap.isOpened():
                time.sleep(0.5)
                cap = cv2.VideoCapture(self.stream_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                continue

            ret, frame = cap.read()
            now = time.time()

            if not ret or frame is None or frame.size == 0:
                consecutive_failures += 1
                if consecutive_failures >= 30:
                    logger.warning(f"[CameraWorker] Stream read failed {consecutive_failures} times for {self.camera_id}. Re-opening...")
                    cap.release()
                    time.sleep(0.8)
                    cap = cv2.VideoCapture(self.stream_url)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    consecutive_failures = 0
                time.sleep(0.03)
                continue

            consecutive_failures = 0

            # Apply physical camera rotation if configured
            if self.rotation == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotation == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # Atomic update of latest frame
            with self._frame_lock:
                if self._latest_frame is not None:
                    # Dropping previous stale frame that was not yet rendered/processed
                    self._dropped_frames_total += 1
                self._latest_frame = frame
                self._latest_frame_time = now
                self._frame_seq += 1

            # Camera FPS calculation over 1-second rolling window
            self._cam_fps_count += 1
            dt = now - self._cam_fps_window_start
            if dt >= 1.0:
                self._measured_cam_fps = self._cam_fps_count / dt
                self._cam_fps_count = 0
                self._cam_fps_window_start = now

            # Required runtime diagnostics log (throttled every 3 seconds)
            if now - last_log_time >= 3.0:
                last_log_time = now
                logger.info(
                    f"[USB] Frame received #{self._frame_seq} timestamp={now:.3f} | "
                    f"[STREAM] Buffer size: 1 | Dropped stale frames: {self._dropped_frames_total} | "
                    f"Camera FPS: {self._measured_cam_fps:.1f}"
                )

        cap.release()
        logger.info(f"[CameraWorker] Reader loop exited for {self.camera_id}")

    def _ai_loop(self):
        """
        Decoupled AI inference thread.
        Samples the latest unread frame when ready, runs YOLOv8 + Tracker + ThreatEngine,
        and saves/broadcasts real detections with sensible deduplication.
        If YOLO takes 100-200ms, camera streaming continues at full FPS without waiting!
        """
        last_zone_sync = 0.0
        while not self._stopped:
            # Periodically sync zone geometry dynamically from database
            now_t = time.time()
            if now_t - last_zone_sync >= 3.0:
                self.refresh_zone_from_db()
                last_zone_sync = now_t

            frame_to_process = None
            frame_time = 0.0
            seq = 0

            # Sample latest frame
            with self._frame_lock:
                if self._latest_frame is not None and self._frame_seq > self._last_ai_frame_seq:
                    frame_to_process = self._latest_frame.copy()
                    frame_time = self._latest_frame_time
                    seq = self._frame_seq
                    self._last_ai_frame_seq = seq

            if frame_to_process is None:
                time.sleep(0.01) # Wait briefly for next frame
                continue

            t_start = time.time()
            logger.debug(f"[YOLO] Inference start for {self.camera_id} (frame #{seq})")

            # 1. Run YOLOv8 on all supported classes (Person, Vehicles, Animals)
            raw_dets = self.detector.detect(
                frame_to_process,
                camera_id=self.camera_id,
                track=True,
                conf_threshold=self.conf_threshold
            )

            # 2. Update multi-object tracker for persistent IDs (Person #1, Car #1)
            active_tracks = self.tracker.update(raw_dets)

            # 3. Process spatial zones & loitering in ThreatEngine
            self.threat_engine.process_tracks(
                active_tracks,
                video_id=None,
                frame_bgr=frame_to_process
            )

            t_end = time.time()
            infer_ms = (t_end - t_start) * 1000.0
            self._last_ai_infer_time_ms = infer_ms
            self._measured_latency_ms = max(5.0, (t_end - frame_time) * 1000.0)
            self._latest_tracks = list(active_tracks)
            self._latest_ai_timestamp = t_end

            # Calculate AI FPS over 1-second rolling window
            self._ai_fps_count += 1
            ai_dt = t_end - self._ai_fps_window_start
            if ai_dt >= 1.0:
                self._measured_ai_fps = self._ai_fps_count / ai_dt
                self._ai_fps_count = 0
                self._ai_fps_window_start = t_end

            # Diagnostics log
            logger.info(
                f"[YOLO] Inference end: {infer_ms:.1f}ms | Detection count: {len(raw_dets)} | "
                f"[TRACKER] Active tracks: {len(active_tracks)} | AI FPS: {self._measured_ai_fps:.1f} | "
                f"Latency: {self._measured_latency_ms:.0f}ms"
            )

            # Deduplicated event emission for Detection Log
            self._deduplicate_and_emit_detections(active_tracks, frame_to_process)

        logger.info(f"[CameraWorker] AI loop exited for {self.camera_id}")

    def _deduplicate_and_emit_detections(self, active_tracks: List[TrackedObject], frame_bgr: np.ndarray):
        """
        Sensible deduplication for Detection Log:
        - Logs newly appeared track IDs immediately.
        - Logs on state change (e.g. entered restricted zone or started loitering).
        - Periodic heartbeat log (every 6.0 seconds) for long-lived active tracks.
        """
        now = time.time()

        from ai_engine.intelligence.anpr_engine import get_anpr_engine
        anpr_engine = get_anpr_engine()

        for trk in active_tracks:
            tid = trk.track_id
            is_vehicle = trk.object_type in ["VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE"]
            plate_info = None

            if is_vehicle:
                try:
                    plate_eval = anpr_engine.evaluate_vehicle_plate(
                        frame_bgr=frame_bgr,
                        vehicle_bbox=trk.bbox,
                        camera_id=self.camera_id,
                        track_id=trk.track_id,
                        vehicle_type=trk.object_type
                    )
                    plate_info = plate_eval
                except Exception as ape:
                    logger.debug(f"[CameraWorker] ANPR error: {ape}")

            p_text = plate_info.get("plate_text") if plate_info else ""
            state_key = f"{trk.object_type}_{'RESTRICTED' if trk.in_zone else 'NORMAL'}_{'LOITER' if trk.zone_dwell_time > 10 else ''}_{p_text}"

            last_time = self._logged_tracks.get(tid, 0.0)
            last_state = self._logged_states.get(tid, "")

            is_new = (tid not in self._logged_tracks)
            state_changed = (last_state != state_key)
            periodic_refresh = (now - last_time >= 4.0)

            if is_new or state_changed or periodic_refresh:
                self._logged_tracks[tid] = now
                self._logged_states[tid] = state_key

                # Determine real event type
                if trk.in_zone:
                    event_type = "ZONE_INTRUSION"
                elif plate_info and plate_info.get("plate_status") == "READABLE" and plate_info.get("plate_text"):
                    event_type = "PLATE_DETECTED"
                elif plate_info and plate_info.get("plate_status") == "UNREADABLE":
                    event_type = "UNREADABLE_PLATE"
                elif trk.object_type == "PERSON":
                    event_type = "PERSON_DETECTED"
                else:
                    event_type = f"{trk.object_type}_DETECTED"

                det_data = {
                    "camera_id": self.camera_id,
                    "object_type": trk.object_type,
                    "object_id": trk.object_label,
                    "confidence": trk.confidence,
                    "event_type": event_type,
                    "bbox": trk.bbox,
                    "is_in_restricted_zone": trk.in_zone,
                    "zone": trk.zone_name,
                    "loitering_duration": round(trk.zone_dwell_time, 1) if trk.in_zone else 0.0,
                    "plate_info": plate_info,
                }
                self._handle_detection_event(det_data)

        # Cleanup stale tracks from deduplication memory
        active_ids = {t.track_id for t in active_tracks}
        dead_keys = [k for k in self._logged_tracks.keys() if k not in active_ids and now - self._logged_tracks[k] > 15.0]
        for k in dead_keys:
            self._logged_tracks.pop(k, None)
            self._logged_states.pop(k, None)

    def _handle_detection_event(self, det_data: dict):
        """Persist detection record to DB and broadcast over WebSocket for Detection Log."""
        db = SessionLocal()
        now_dt = datetime.utcnow()
        try:
            bbox = det_data.get("bbox") or {}
            event_type = det_data.get("event_type") or "PERSON_DETECTED"
            obj_id = det_data.get("object_id") or "Track #1"
            plate_info = det_data.get("plate_info")
            p_box = plate_info.get("plate_bbox") if plate_info else None
            p_text = plate_info.get("plate_text") if plate_info else None
            p_conf = plate_info.get("plate_confidence") if plate_info else None
            p_status = plate_info.get("plate_status") if plate_info else None

            rec = DB_Detection(
                id=str(uuid.uuid4()),
                camera_id=self.camera_id,
                video_id=None,
                session_id=self.session_id,
                object_type=det_data.get("object_type", "PERSON"),
                object_id=obj_id,
                confidence=det_data.get("confidence", 0.0),
                zone=det_data.get("zone"),
                event_type=event_type,
                bbox_x=bbox.get("x", 0.0),
                bbox_y=bbox.get("y", 0.0),
                bbox_w=bbox.get("w", 0.0),
                bbox_h=bbox.get("h", 0.0),
                is_in_restricted_zone=det_data.get("is_in_restricted_zone", False),
                loitering_duration=det_data.get("loitering_duration"),
                timestamp=now_dt,
                plate_text=p_text,
                plate_confidence=p_conf,
                plate_status=p_status,
                plate_bbox_x=p_box.get("x") if p_box else None,
                plate_bbox_y=p_box.get("y") if p_box else None,
                plate_bbox_w=p_box.get("w") if p_box else None,
                plate_bbox_h=p_box.get("h") if p_box else None,
            )
            db.add(rec)

            # Record readable ANPR Event & check Watchlist
            if p_status == "READABLE" and p_text:
                anpr_rec = ANPREvent(
                    id=str(uuid.uuid4()),
                    camera_id=self.camera_id,
                    vehicle_track_id=int(obj_id.split("#")[-1]) if "#" in obj_id else 1,
                    vehicle_type=det_data.get("object_type", "CAR"),
                    plate_text=p_text,
                    plate_confidence=p_conf,
                    plate_status="READABLE",
                    bbox_x=p_box.get("x", bbox.get("x", 0.0)) if p_box else bbox.get("x", 0.0),
                    bbox_y=p_box.get("y", bbox.get("y", 0.0)) if p_box else bbox.get("y", 0.0),
                    bbox_w=p_box.get("w", bbox.get("w", 0.0)) if p_box else bbox.get("w", 0.0),
                    bbox_h=p_box.get("h", bbox.get("h", 0.0)) if p_box else bbox.get("h", 0.0),
                    timestamp=now_dt
                )
                db.add(anpr_rec)

                # Check Watchlist Plate Match
                norm_plate = p_text.replace(" ", "").upper()
                wl_match = db.query(WatchlistPlate).filter(
                    WatchlistPlate.is_active == True,
                    WatchlistPlate.plate_number == norm_plate
                ).first()
                if wl_match:
                    alert_id_str = f"ALERT-{now_dt.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
                    wl_alert = Alert(
                        id=str(uuid.uuid4()),
                        alert_id=alert_id_str,
                        camera_id=self.camera_id,
                        event_type="WATCHLIST_PLATE_MATCH",
                        object_type="VEHICLE",
                        object_id=f"{obj_id} (Plate: {p_text})",
                        threat_level=wl_match.threat_priority or "HIGH",
                        reason=f"SUSPECT VEHICLE PLATE DETECTED: {p_text} ({wl_match.vehicle_owner or wl_match.reason or 'Wanted vehicle'}) detected on {self.camera_id} with {p_conf:.1f}% OCR confidence.",
                        confidence=p_conf,
                        bbox_x=bbox.get("x", 0.0),
                        bbox_y=bbox.get("y", 0.0),
                        bbox_w=bbox.get("w", 0.0),
                        bbox_h=bbox.get("h", 0.0),
                        status="NEW",
                        created_at=now_dt,
                        updated_at=now_dt,
                    )
                    db.add(wl_alert)
                    manager.broadcast_sync({
                        "type": "NEW_ALERT",
                        "data": {
                            "id": wl_alert.id,
                            "alert_id": wl_alert.alert_id,
                            "camera_id": self.camera_id,
                            "event_type": "WATCHLIST_PLATE_MATCH",
                            "object_id": wl_alert.object_id,
                            "threat_level": wl_alert.threat_level,
                            "reason": wl_alert.reason,
                            "timestamp": now_dt.isoformat(),
                        }
                    })

            db.commit()

            ws_payload = {
                "id": rec.id,
                "camera_id": self.camera_id,
                "session_id": self.session_id,
                "object_type": rec.object_type,
                "object_id": rec.object_id,
                "confidence": rec.confidence,
                "zone": rec.zone,
                "event_type": event_type,
                "bbox": bbox,
                "is_in_restricted_zone": rec.is_in_restricted_zone,
                "loitering_duration": rec.loitering_duration,
                "plate_info": plate_info,
                "timestamp": now_dt.isoformat(),
            }
            manager.broadcast_sync({
                "type": "DETECTION",
                "data": ws_payload,
                "timestamp": now_dt.isoformat(),
            })
            logger.info(f"[WS] Detection sent: {obj_id} ({rec.confidence:.1f}%) for {self.camera_id}")
        except Exception as e:
            logger.warning(f"[CameraWorker] Error persisting detection: {e}")
        finally:
            db.close()

    def get_metrics(self) -> Dict[str, Any]:
        """Return actual measured runtime metrics."""
        now = time.time()
        ai_active = (now - self._latest_ai_timestamp < 4.0)
        return {
            "camera_id": self.camera_id,
            "session_id": self.session_id,
            "session_start_time": self.session_start_time,
            "camera_fps": round(self._measured_cam_fps, 1),
            "ai_fps": round(self._measured_ai_fps, 1) if ai_active else 0.0,
            "latency_ms": round(self._measured_latency_ms, 0) if ai_active else (round((now - self._latest_frame_time)*1000, 0) if self._latest_frame_time > 0 else 0.0),
            "inference_time_ms": round(self._last_ai_infer_time_ms, 1) if ai_active else 0.0,
            "dropped_stale_frames": self._dropped_frames_total,
            "active_tracks": len(self._latest_tracks) if ai_active else 0,
            "ai_status": "RUNNING" if ai_active else "OFFLINE",
            "conf_threshold": round(self.conf_threshold * 100, 1),
            "rotation": self.rotation,
            "source_type": self.source_type,
            "active_viewers": self._active_viewers
        }

    def generate_mjpeg(self):
        """
        High-frame-rate MJPEG streaming generator for client browser.
        Fetches the latest available frame, paints cached tracking overlays and HUD,
        and yields JPEG bytes immediately without blocking on YOLO inference.
        """
        self._active_viewers += 1
        self._last_viewer_time = time.time()

        try:
            last_sent_seq = -1
            while not self._stopped:
                frame = None
                with self._frame_lock:
                    if self._latest_frame is not None:
                        frame = self._latest_frame.copy()
                        last_sent_seq = self._frame_seq

                if frame is None:
                    # Waiting for initial stream connection
                    h_disp, w_disp = 480, 640
                    placeholder = np.zeros((h_disp, w_disp, 3), dtype=np.uint8)
                    placeholder[:] = (20, 24, 30)
                    tag = "USB Camera Connecting..." if self.is_usb else "CCTV Signal Connecting..."
                    cv2.putText(placeholder, tag, (60, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 165, 255), 2)
                    cv2.putText(placeholder, f"Target: {self.stream_url}", (60, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 140), 1)
                    ret_enc, jpeg = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    if ret_enc:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                    time.sleep(0.5)
                    continue

                h_f, w_f = frame.shape[:2]

                # 1. Draw configured restricted zone if present
                if self.threat_engine.zone_polygon is not None and self.threat_engine.zone_coords:
                    try:
                        pts = []
                        for coord in self.threat_engine.zone_coords:
                            px = int((coord[0] / 100.0) * w_f)
                            py = int((coord[1] / 100.0) * h_f)
                            pts.append([px, py])
                        pts_arr = np.array(pts, np.int32).reshape((-1, 1, 2))
                        # Red polygon with semi-transparent overlay
                        overlay = frame.copy()
                        cv2.fillPoly(overlay, [pts_arr], color=(0, 0, 180))
                        cv2.addWeighted(overlay, 0.22, frame, 0.78, 0, frame)
                        cv2.polylines(frame, [pts_arr], isClosed=True, color=(0, 0, 255), thickness=2)
                        cv2.putText(
                            frame,
                            f"RESTRICTED ZONE: {self.threat_engine.zone_name}",
                            (pts[0][0], max(20, pts[0][1] - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 0, 255),
                            2
                        )
                    except Exception as ze:
                        pass

                # 2. Draw cached active YOLO tracks with persistent IDs & real confidence
                now = time.time()
                ai_active = (now - self._latest_ai_timestamp < 4.0)

                if ai_active:
                    for trk in self._latest_tracks:
                        x1, y1, x2, y2 = trk.bbox["x"], trk.bbox["y"], trk.bbox["w"], trk.bbox["h"]
                        px1 = int((x1 / 100.0) * w_f)
                        py1 = int((y1 / 100.0) * h_f)
                        pw = int((x2 / 100.0) * w_f)
                        ph = int((y2 / 100.0) * h_f)

                        # Color coding: Red if restricted intrusion, Amber if loitering, Emerald if normal
                        if trk.in_zone:
                            color = (0, 0, 255) # Red
                            extra_tag = " [RESTRICTED]"
                            if trk.zone_dwell_time > 10.0:
                                color = (0, 140, 255) # Amber
                                extra_tag = f" [LOITERING {int(trk.zone_dwell_time)}s]"
                        else:
                            color = (0, 255, 64) # Emerald
                            extra_tag = ""

                        # Bounding box
                        cv2.rectangle(frame, (px1, py1), (px1 + pw, py1 + ph), color, 2)

                        # Label badge
                        label = f"{trk.object_label.upper()} — {trk.confidence:.1f}%{extra_tag}"
                        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
                        # Text background box
                        cv2.rectangle(frame, (px1, max(0, py1 - th - 8)), (px1 + tw + 6, py1), color, -1)
                        # Text in black for high contrast
                        cv2.putText(frame, label, (px1 + 3, max(12, py1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 1, cv2.LINE_AA)

                # 3. HUD telemetry overlay with measured runtime metrics
                badge = "USB LIVE" if self.is_usb else "CCTV LIVE"
                cv2.putText(frame, f"[SHIELD {badge}]", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 128), 2)

                if ai_active:
                    metrics_txt = f"CAM: {self._measured_cam_fps:.1f} FPS | AI: {self._measured_ai_fps:.1f} FPS | LATENCY: {self._measured_latency_ms:.0f}ms"
                    cv2.putText(frame, metrics_txt, (15, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
                else:
                    cv2.putText(frame, "AI PROCESSING: OFFLINE", (15, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 140, 255), 1)

                # Time stamp
                ts_str = datetime.now().strftime("%H:%M:%S")
                cv2.putText(frame, ts_str, (w_f - 95, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                # Encode to JPEG
                ret_enc, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
                if not ret_enc:
                    continue

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

                # Smooth pacing ~25 FPS
                time.sleep(0.04)

        except GeneratorExit:
            pass
        finally:
            self._active_viewers = max(0, self._active_viewers - 1)
            self._last_viewer_time = time.time()


class CameraStreamManager:
    """
    Singleton manager for camera stream workers.
    Ensures single VideoCapture per active camera, shared across all web clients.
    """

    def __init__(self):
        self._workers: Dict[str, CameraStreamWorker] = {}
        self._lock = threading.Lock()

    def get_or_create_worker(
        self,
        camera_id: str,
        stream_url: str,
        source_type: str = "USB_PHONE",
        conf_threshold: float = 0.30,
        rotation: Optional[int] = None
    ) -> CameraStreamWorker:
        with self._lock:
            worker = self._workers.get(camera_id)
            if worker is not None:
                # If stream URL changed, restart worker
                if worker.stream_url != stream_url or worker._stopped:
                    logger.info(f"[CameraStreamManager] Restarting worker for {camera_id} with new URL: {stream_url}")
                    worker.stop()
                    worker = CameraStreamWorker(
                        camera_id=camera_id,
                        stream_url=stream_url,
                        source_type=source_type,
                        conf_threshold=conf_threshold,
                        rotation=rotation or 0
                    )
                    self._workers[camera_id] = worker
                else:
                    # Update dynamic threshold if changed
                    worker.set_confidence(conf_threshold)
                    if rotation is not None:
                        worker.set_rotation(rotation)
                return worker

            # Create new worker
            logger.info(f"[CameraStreamManager] Creating new worker for {camera_id} -> {stream_url} (rotation={rotation or 0})")
            worker = CameraStreamWorker(
                camera_id=camera_id,
                stream_url=stream_url,
                source_type=source_type,
                conf_threshold=conf_threshold,
                rotation=rotation or 0
            )
            self._workers[camera_id] = worker
            return worker

    def get_worker(self, camera_id: str) -> Optional[CameraStreamWorker]:
        with self._lock:
            return self._workers.get(camera_id)

    def refresh_worker_zone(self, camera_id: str):
        with self._lock:
            worker = self._workers.get(camera_id)
            if worker:
                worker.refresh_zone_from_db()
                logger.info(f"[CameraStreamManager] Refreshed zone for worker {camera_id}")

    def stop_worker(self, camera_id: str):
        with self._lock:
            worker = self._workers.pop(camera_id, None)
            if worker:
                worker.stop()

    def stop_all(self):
        with self._lock:
            for w in self._workers.values():
                w.stop()
            self._workers.clear()


# Global singleton instance
camera_stream_manager = CameraStreamManager()
