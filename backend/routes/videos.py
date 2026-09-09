from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from database.database import get_db, SessionLocal
from models.models import Video, Detection, Alert, Zone, ANPREvent
from schemas.schemas import VideoResponse
from websocket.manager import manager
from datetime import datetime, timedelta
import uuid, os, shutil, threading, logging, sys, time, json
import cv2
import numpy as np

logger = logging.getLogger("video_route")

# Add project root so ai_engine can be imported cleanly
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

router = APIRouter()

# Storage path (relative to repo root)
STORAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "storage", "videos"
)
os.makedirs(STORAGE_DIR, exist_ok=True)

# ─── Shared Detector Singleton & In-Memory Job Registry ───────────────────────
_detector_lock = threading.Lock()
_shared_detector = None

def get_shared_detector():
    """Singleton helper to ensure YOLOv8 model is loaded only once across the app."""
    global _shared_detector
    with _detector_lock:
        if _shared_detector is None:
            from ai_engine.detection.detector import Detector
            model_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "models", "yolov8n.pt"
            )
            logger.info(f"[VideoAI] Initializing shared Detector from {model_path}...")
            _shared_detector = Detector(model_path=model_path, conf_threshold=0.25)
            logger.info("[VideoAI] Shared Detector initialized successfully.")
        return _shared_detector


# Active video processing jobs & progress
_video_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()


def run_video_inference_worker(video_id: str, file_path: str, camera_id: str = "BOP-07"):
    """
    High-performance background worker running real YOLOv8 inference on uploaded CCTV footage.
    Uses configurable frame sampling (default: 5–6 analysis frames/sec) to prevent slow 
    blocking loops while maintaining exact video-relative timestamps (T+XX.Xs) and tracking continuity.
    """
    with _jobs_lock:
        job_data = _video_jobs.get(video_id)
        if not job_data:
            job_data = {
                "video_id": video_id,
                "status": "PROCESSING",
                "progress": 0,
                "current_frame": 0,
                "total_frames": 0,
                "fps": 25.0,
                "analysis_fps": 5.0,
                "duration": 0.0,
                "detections": 0,
                "tracks": 0,
                "events": 0,
                "low_light": False,
                "brightness": 0.0,
                "raw_video_url": None,
                "enhanced_video_url": None,
                "error": None,
                "cancel_requested": False
            }
            _video_jobs[video_id] = job_data

    db = SessionLocal()
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        with _jobs_lock:
            _video_jobs.pop(video_id, None)
        db.close()
        return

    video.status = "AI_ANALYZING"
    db.commit()

    with _jobs_lock:
        job_data["status"] = "AI_ANALYZING"

    cap = None
    enhanced_writer = None
    try:
        from shapely.geometry import Point
        from ai_engine.tracking.tracker import Tracker
        from ai_engine.intelligence.threat_engine import ThreatEngine, DEFAULT_RESTRICTED_ZONE_A

        detector = get_shared_detector()
        tracker = Tracker()

        # Look up optional zone explicitly configured for this specific video, or fallback to camera/default zone
        video_zone = db.query(Zone).filter(Zone.source_id == video_id, Zone.enabled == True).first()
        if not video_zone and camera_id:
            video_zone = db.query(Zone).filter(Zone.source_id == camera_id, Zone.enabled == True).first()

        v_coords = None
        v_zone_name = None
        if video_zone and video_zone.coordinates_json:
            try:
                v_coords = json.loads(video_zone.coordinates_json)
                v_zone_name = video_zone.name
            except Exception as ze:
                logger.warning(f"[VideoAI] Failed to parse zone for video {video_id}: {ze}")

        if not v_coords:
            v_coords = DEFAULT_RESTRICTED_ZONE_A
            v_zone_name = "Restricted Zone A"

        from routes.watchlist import _load_active_watchlist_records
        from ai_engine.intelligence.face_engine import get_face_engine
        from ai_engine.intelligence.anpr_engine import get_anpr_engine
        from ai_engine.preprocessing.frame_enhancer import FrameEnhancer
        from models.models import ANPREvent, WatchlistPlate

        face_engine = get_face_engine()
        anpr_engine = get_anpr_engine()
        anpr_engine.clear_cache()
        enhancer = FrameEnhancer()
        watchlist_records = _load_active_watchlist_records(db)

        # Load active vehicle plate watchlist records
        active_plates = db.query(WatchlistPlate).filter(WatchlistPlate.is_active == True).all()
        watchlist_plate_map = {p.plate_number.replace(" ", "").upper(): p for p in active_plates}


        threat_engine = ThreatEngine(
            camera_id=camera_id,
            backend_url="http://localhost:8000",
            loitering_threshold=15.0,
            restricted_zone_polygon=v_coords,
            zone_name=v_zone_name
        )

        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise RuntimeError(f"OpenCV could not open video file at {file_path}")

        source_fps   = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration     = round(total_frames / source_fps, 2) if source_fps > 0 else 0.0

        video.duration = duration
        db.commit()

        # Target analysis FPS (5.0 FPS provides smooth tracking while running ~5x faster than 30fps)
        target_fps = 5.0
        sample_step = max(1, int(round(source_fps / target_fps)))

        # Check initial frames to determine if video is in low-light condition
        sample_brightness = []
        for _ in range(min(5, total_frames)):
            ret_s, f_s = cap.read()
            if ret_s:
                sample_brightness.append(enhancer.get_brightness(f_s))
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        initial_avg_brightness = float(np.mean(sample_brightness)) if sample_brightness else 100.0
        is_video_low_light = (initial_avg_brightness < enhancer.enter_threshold)
        logger.info(f"[VideoAI] Video {video_id} luminance check: brightness={initial_avg_brightness:.1f} (low_light={is_video_low_light})")

        enhanced_writer = None
        enhanced_filename = f"{video_id}_enhanced.mp4"
        enhanced_file_path = os.path.join(STORAGE_DIR, enhanced_filename)
        raw_video_url = f"/storage/videos/{os.path.basename(file_path)}"
        enhanced_video_url = f"/storage/videos/{enhanced_filename}" if is_video_low_light else None

        if is_video_low_light:
            try:
                import imageio_ffmpeg
                enhanced_writer = imageio_ffmpeg.write_frames(
                    enhanced_file_path,
                    (width, height),
                    fps=source_fps,
                    codec="libx264",
                    pix_fmt_in="bgr24",
                    macro_block_size=1,
                    output_params=["-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p"],
                    ffmpeg_log_level="error"
                )
                enhanced_writer.send(None)
                logger.info(f"[VideoAI] Initialized H.264 enhanced video writer: {enhanced_filename}")
            except Exception as we:
                logger.warning(f"[VideoAI] Failed to init H.264 writer: {we}")
                enhanced_writer = None

        with _jobs_lock:
            job_data["total_frames"] = total_frames
            job_data["fps"] = round(source_fps, 1)
            job_data["analysis_fps"] = round(source_fps / sample_step, 1)
            job_data["duration"] = duration
            job_data["low_light"] = is_video_low_light
            job_data["brightness"] = round(initial_avg_brightness, 1)
            job_data["raw_video_url"] = raw_video_url
            job_data["enhanced_video_url"] = enhanced_video_url

        logger.info(
            f"[VideoAI] Processing video {video_id}: {total_frames} frames @ {source_fps:.1f} FPS "
            f"({duration}s, {width}x{height}), sampling step = {sample_step} (effective {job_data['analysis_fps']} FPS)"
        )

        frame_idx = 0
        wall_start = datetime.utcnow()
        alerted_tracks = set()
        total_detections_count = 0
        events_count = 0
        last_ws_broadcast = time.time()

        while True:
            # Check for cancellation
            with _jobs_lock:
                if job_data.get("cancel_requested", False):
                    logger.info(f"[VideoAI] Analysis for {video_id} cancelled by user request.")
                    video.status = "CANCELLED"
                    job_data["status"] = "CANCELLED"
                    db.commit()
                    manager.broadcast_sync({
                        "type": "VIDEO_STATUS",
                        "data": {"video_id": video_id, "status": "CANCELLED", "progress": 0}
                    })
                    break

            ret, frame = cap.read()
            if not ret:
                break

            current_frame_idx = frame_idx
            frame_idx += 1

            # Update in-memory job progress for current frame immediately
            pct = min(99, int((frame_idx / max(1, total_frames)) * 100))
            with _jobs_lock:
                job_data["current_frame"] = frame_idx
                job_data["progress"] = pct

            # Dual-frame strategy: raw_frame untouched, frame_for_inference enhanced if low-light
            raw_frame = frame
            if is_video_low_light:
                frame_for_inference, was_enhanced, enh_meta = enhancer.enhance(raw_frame)
                if enhanced_writer is not None:
                    try:
                        enhanced_writer.send(frame_for_inference.tobytes())
                    except Exception as ew_err:
                        logger.debug(f"[VideoAI] Error writing enhanced frame: {ew_err}")
            else:
                frame_for_inference = raw_frame
                was_enhanced = False
                enh_meta = {"brightness": initial_avg_brightness, "gamma": 1.0}

            # Adaptive frame sampling: only run YOLO on sampled frames
            if (current_frame_idx % sample_step) != 0 and current_frame_idx != 0:
                continue

            # Ground-truth video-relative timeline timestamp (T+XX.Xs)
            video_time_sec = current_frame_idx / source_fps
            frame_timestamp = wall_start + timedelta(seconds=video_time_sec)

            # 1. Run real YOLOv8 inference on inference frame
            dets = detector.detect(frame_for_inference, camera_id=camera_id, track=True)

            # 2. Update persistent tracker
            active_tracks = tracker.update(dets)

            if current_frame_idx % (sample_step * 3) == 0 or current_frame_idx == 0:
                logger.info(
                    f"[YOLO] frame={current_frame_idx} detections={len(dets)} | "
                    f"[TRACKER] tracks={len(active_tracks)}"
                )

            # 3. Save detection records with video timeline
            for track in active_tracks:
                bx, by = track.bottom_center
                is_in_zone = threat_engine.zone_polygon.contains(Point(bx, by)) if threat_engine.zone_polygon is not None else False

                event_type = "PERSON_DETECTED"
                face_match_data = None
                if track.object_type == "PERSON" and watchlist_records:
                    face_eval = face_engine.evaluate_person_track_face(
                        frame_bgr=raw_frame,
                        person_bbox=track.bbox,
                        camera_id=camera_id,
                        track_id=track.track_id,
                        watchlist_records=watchlist_records,
                        threshold=0.45
                    )
                    if face_eval.get("is_match"):
                        event_type = "WATCHLIST_MATCH"
                        face_match_data = face_eval
                        watchlist_key = f"watchlist_{face_eval['person_id']}_{track.track_id}"
                        if watchlist_key not in alerted_tracks:
                            alerted_tracks.add(watchlist_key)
                            events_count += 1
                            alert_id_str = f"ALERT-{frame_timestamp.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
                            threat_lvl = "CRITICAL" if (is_in_zone or face_eval.get("threat_priority") == "CRITICAL") else (face_eval.get("threat_priority") or "HIGH")
                            alert_rec = Alert(
                                id=str(uuid.uuid4()),
                                alert_id=alert_id_str,
                                camera_id=camera_id,
                                video_id=video_id,
                                event_type="WATCHLIST_MATCH",
                                object_type="PERSON",
                                object_id=f"{face_eval['person_name']} (Track #{track.track_id})",
                                threat_level=threat_lvl,
                                reason=f"WATCHLIST MATCH: {face_eval['person_name']} ({face_eval.get('identifier') or 'POI'}) detected in video at T+{video_time_sec:.1f}s with {face_eval['similarity']:.1f}% face match similarity.",
                                confidence=face_eval["similarity"],
                                bbox_x=track.bbox.get("x", 0.0),
                                bbox_y=track.bbox.get("y", 0.0),
                                bbox_w=track.bbox.get("w", 0.0),
                                bbox_h=track.bbox.get("h", 0.0),
                                status="NEW",
                                created_at=frame_timestamp,
                                updated_at=frame_timestamp,
                            )
                            db.add(alert_rec)

                if is_in_zone and threat_engine.zone_name:
                    event_type = "ZONE_INTRUSION"
                plate_info = None
                if track.object_type in ["VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE"]:
                    plate_eval = anpr_engine.evaluate_vehicle_plate(
                        frame_bgr=frame_for_inference,
                        vehicle_bbox=track.bbox,
                        camera_id=camera_id,
                        track_id=track.track_id,
                        vehicle_type=track.object_label.split(" ")[0].upper() if " " in track.object_label else "CAR"
                    )
                    plate_info = plate_eval
                    logger.info(
                        f"[ANPR] track={track.track_id} plate_detected={plate_eval.get('plate_detected')} status={plate_eval.get('plate_status')} | "
                        f"[OCR] text={plate_eval.get('plate_text')} confidence={plate_eval.get('plate_confidence')}"
                    )

                    p_bbox = plate_eval.get("plate_bbox") or {}
                    p_text = plate_eval.get("plate_text")
                    p_conf = plate_eval.get("plate_confidence")
                    p_status = plate_eval.get("plate_status", "NOT_DETECTED")

                    # Handle READABLE Plate
                    if p_status == "READABLE" and p_text:
                        anpr_key = f"anpr_{camera_id}_{track.track_id}_{p_text}"
                        if anpr_key not in alerted_tracks:
                            alerted_tracks.add(anpr_key)
                            events_count += 1
                            anpr_rec = ANPREvent(
                                id=str(uuid.uuid4()),
                                camera_id=camera_id,
                                video_id=video_id,
                                vehicle_track_id=track.track_id,
                                vehicle_type=plate_eval.get("vehicle_type", "CAR"),
                                plate_text=p_text,
                                plate_confidence=p_conf,
                                plate_status="READABLE",
                                bbox_x=p_bbox.get("x", track.bbox.get("x", 0.0)),
                                bbox_y=p_bbox.get("y", track.bbox.get("y", 0.0)),
                                bbox_w=p_bbox.get("w", track.bbox.get("w", 0.0)),
                                bbox_h=p_bbox.get("h", track.bbox.get("h", 0.0)),
                                video_time_sec=round(video_time_sec, 4),
                                timestamp=frame_timestamp
                            )
                            db.add(anpr_rec)

                            # Watchlist Plate Match Security Alert
                            normalized_search = p_text.replace(" ", "").upper()
                            if normalized_search in watchlist_plate_map:
                                wl_plate = watchlist_plate_map[normalized_search]
                                alert_id_str = f"ALERT-{frame_timestamp.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
                                alert_rec = Alert(
                                    id=str(uuid.uuid4()),
                                    alert_id=alert_id_str,
                                    camera_id=camera_id,
                                    video_id=video_id,
                                    event_type="WATCHLIST_PLATE_MATCH",
                                    object_type="VEHICLE",
                                    object_id=f"{track.object_label} (Plate: {p_text})",
                                    threat_level=wl_plate.threat_priority or "HIGH",
                                    reason=f"SUSPECT VEHICLE PLATE DETECTED: {p_text} ({wl_plate.vehicle_owner or wl_plate.reason or 'Wanted vehicle'}) detected at T+{video_time_sec:.1f}s with {p_conf:.1f}% OCR confidence.",
                                    confidence=p_conf,
                                    bbox_x=track.bbox.get("x", 0.0),
                                    bbox_y=track.bbox.get("y", 0.0),
                                    bbox_w=track.bbox.get("w", 0.0),
                                    bbox_h=track.bbox.get("h", 0.0),
                                    status="NEW",
                                    created_at=frame_timestamp,
                                    updated_at=frame_timestamp,
                                )
                                db.add(alert_rec)

                            manager.broadcast_sync({
                                "type": "ANPR_EVENT",
                                "data": {
                                    "camera_id": camera_id,
                                    "video_id": video_id,
                                    "vehicle_track_id": track.track_id,
                                    "vehicle_label": track.object_label,
                                    "vehicle_type": plate_eval.get("vehicle_type", "CAR"),
                                    "plate_text": p_text,
                                    "plate_confidence": p_conf,
                                    "plate_status": "READABLE",
                                    "video_time_sec": round(video_time_sec, 2),
                                    "timestamp": frame_timestamp.isoformat(),
                                    "bbox": track.bbox if hasattr(track, "bbox") and track.bbox else {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
                                    "plate_bbox": p_bbox if p_bbox else None
                                }
                            })

                    # Handle UNREADABLE Plate candidate (honestly logged, zero hallucination)
                    elif p_status in ["UNREADABLE", "UNCERTAIN"]:
                        anpr_unreadable_key = f"anpr_unreadable_{camera_id}_{track.track_id}"
                        if anpr_unreadable_key not in alerted_tracks:
                            alerted_tracks.add(anpr_unreadable_key)
                            events_count += 1
                            anpr_rec = ANPREvent(
                                id=str(uuid.uuid4()),
                                camera_id=camera_id,
                                video_id=video_id,
                                vehicle_track_id=track.track_id,
                                vehicle_type=plate_eval.get("vehicle_type", "CAR"),
                                plate_text=None,
                                plate_confidence=None,
                                plate_status="UNREADABLE",
                                bbox_x=p_bbox.get("x", track.bbox.get("x", 0.0)),
                                bbox_y=p_bbox.get("y", track.bbox.get("y", 0.0)),
                                bbox_w=p_bbox.get("w", track.bbox.get("w", 0.0)),
                                bbox_h=p_bbox.get("h", track.bbox.get("h", 0.0)),
                                video_time_sec=round(video_time_sec, 4),
                                timestamp=frame_timestamp
                            )
                            db.add(anpr_rec)

                            manager.broadcast_sync({
                                "type": "ANPR_EVENT",
                                "data": {
                                    "camera_id": camera_id,
                                    "video_id": video_id,
                                    "vehicle_track_id": track.track_id,
                                    "vehicle_label": track.object_label,
                                    "vehicle_type": plate_eval.get("vehicle_type", "CAR"),
                                    "plate_text": None,
                                    "plate_confidence": None,
                                    "plate_status": "UNREADABLE",
                                    "video_time_sec": round(video_time_sec, 2),
                                    "timestamp": frame_timestamp.isoformat(),
                                    "bbox": track.bbox if hasattr(track, "bbox") and track.bbox else {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0},
                                    "plate_bbox": p_bbox if p_bbox else None
                                }
                            })

                if is_in_zone and threat_engine.zone_name:
                    event_type = "ZONE_INTRUSION"
                elif plate_info and plate_info.get("plate_status") == "READABLE":
                    event_type = "PLATE_DETECTED"
                elif plate_info and plate_info.get("plate_status") == "UNREADABLE":
                    event_type = "UNREADABLE_PLATE"
                elif track.object_type in ["VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE"]:
                    event_type = f"{track.object_type}_DETECTED"

                det_label = track.object_label
                if face_match_data:
                    det_label = f"{face_match_data['person_name']} ({track.object_label})"

                p_box = plate_info.get("plate_bbox") if plate_info else None
                det_rec = Detection(
                    id                    = str(uuid.uuid4()),
                    camera_id             = camera_id,
                    video_id              = video_id,
                    object_type           = track.object_type,
                    object_id             = det_label,
                    confidence            = round(track.confidence, 1),
                    zone                  = threat_engine.zone_name if is_in_zone else None,
                    event_type            = event_type,
                    bbox_x                = track.bbox["x"],
                    bbox_y                = track.bbox["y"],
                    bbox_w                = track.bbox["w"],
                    bbox_h                = track.bbox["h"],
                    is_in_restricted_zone = is_in_zone,
                    loitering_duration    = int(track.zone_dwell_time) if is_in_zone else None,
                    timestamp             = frame_timestamp,
                    frame_index           = current_frame_idx,
                    video_time_sec        = round(video_time_sec, 4),
                    plate_text            = plate_info.get("plate_text") if plate_info else None,
                    plate_confidence      = plate_info.get("plate_confidence") if plate_info else None,
                    plate_status          = plate_info.get("plate_status") if plate_info else None,
                    plate_bbox_x          = p_box.get("x") if p_box else None,
                    plate_bbox_y          = p_box.get("y") if p_box else None,
                    plate_bbox_w          = p_box.get("w") if p_box else None,
                    plate_bbox_h          = p_box.get("h") if p_box else None,
                )
                db.add(det_rec)
                total_detections_count += 1

                # Broadcast live detection event to WebSocket clients
                if (track.track_id not in alerted_tracks) or (current_frame_idx % (sample_step * 5) == 0):
                    manager.broadcast_sync({
                        "type": "DETECTION",
                        "data": {
                            "id": det_rec.id,
                            "camera_id": camera_id,
                            "video_id": video_id,
                            "object_type": det_rec.object_type,
                            "object_id": det_rec.object_id,
                            "confidence": det_rec.confidence,
                            "bbox": {
                                "x": det_rec.bbox_x,
                                "y": det_rec.bbox_y,
                                "w": det_rec.bbox_w,
                                "h": det_rec.bbox_h
                            },
                            "event_type": det_rec.event_type,
                            "timestamp": det_rec.timestamp.isoformat() if hasattr(det_rec.timestamp, "isoformat") else str(det_rec.timestamp),
                            "video_time_sec": det_rec.video_time_sec,
                            "is_in_restricted_zone": det_rec.is_in_restricted_zone,
                            "loitering_duration": det_rec.loitering_duration,
                            "plate_info": {
                                "plate_detected": bool(plate_info and plate_info.get("plate_detected")),
                                "plate_text": plate_info.get("plate_text") if plate_info else None,
                                "plate_confidence": plate_info.get("plate_confidence") if plate_info else None,
                                "plate_status": plate_info.get("plate_status") if plate_info else None,
                                "bbox": p_box if p_box else None
                            } if plate_info else None
                        }
                    })


                # Real Alert Generation upon Zone Intrusion
                if is_in_zone and threat_engine.zone_name and track.object_type in ["PERSON", "VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE"]:
                    if track.track_id not in alerted_tracks:
                        alerted_tracks.add(track.track_id)
                        events_count += 1
                        alert_id_str = f"ALERT-{frame_timestamp.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
                        alert_rec = Alert(
                            id=str(uuid.uuid4()),
                            alert_id=alert_id_str,
                            camera_id=camera_id,
                            video_id=video_id,
                            event_type="ZONE_INTRUSION",
                            object_type=track.object_type,
                            object_id=track.object_label,
                            threat_level="HIGH" if track.object_type == "PERSON" else "CRITICAL",
                            reason=f"{track.object_label} entered {threat_engine.zone_name} in uploaded video at T+{video_time_sec:.1f}s.",
                            confidence=round(track.confidence, 1),
                            bbox_x=track.bbox.get("x", 0.0),
                            bbox_y=track.bbox.get("y", 0.0),
                            bbox_w=track.bbox.get("w", 0.0),
                            bbox_h=track.bbox.get("h", 0.0),
                            status="NEW",
                            created_at=frame_timestamp,
                            updated_at=frame_timestamp,
                        )
                        db.add(alert_rec)

                # Real Alert Generation upon Loitering
                if is_in_zone and threat_engine.zone_name and track.zone_dwell_time >= threat_engine.loitering_threshold:
                    loiter_key = f"loiter_{track.track_id}"
                    if loiter_key not in alerted_tracks:
                        alerted_tracks.add(loiter_key)
                        events_count += 1
                        alert_id_str = f"ALERT-{frame_timestamp.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
                        alert_rec = Alert(
                            id=str(uuid.uuid4()),
                            alert_id=alert_id_str,
                            camera_id=camera_id,
                            video_id=video_id,
                            event_type="LOITERING",
                            object_type=track.object_type,
                            object_id=track.object_label,
                            threat_level="CRITICAL",
                            reason=f"{track.object_label} loitered in {threat_engine.zone_name} for {int(track.zone_dwell_time)}s at T+{video_time_sec:.1f}s.",
                            confidence=round(track.confidence, 1),
                            bbox_x=track.bbox.get("x", 0.0),
                            bbox_y=track.bbox.get("y", 0.0),
                            bbox_w=track.bbox.get("w", 0.0),
                            bbox_h=track.bbox.get("h", 0.0),
                            status="NEW",
                            created_at=frame_timestamp,
                            updated_at=frame_timestamp,
                        )
                        db.add(alert_rec)

            # Update in-memory job progress
            pct = min(99, int((frame_idx / max(1, total_frames)) * 100))
            with _jobs_lock:
                job_data["progress"] = pct
                job_data["current_frame"] = frame_idx
                job_data["detections"] = total_detections_count
                job_data["tracks"] = len(active_tracks)
                job_data["events"] = events_count
                job_data["low_light"] = is_video_low_light
                job_data["brightness"] = round(enh_meta.get("brightness", initial_avg_brightness), 1)

            # Broadcast WebSocket progress every 0.25 seconds
            now_ts = time.time()
            if (now_ts - last_ws_broadcast) >= 0.25:
                last_ws_broadcast = now_ts
                manager.broadcast_sync({
                    "type": "VIDEO_PROGRESS",
                    "data": {
                        "video_id": video_id,
                        "status": "AI_ANALYZING",
                        "progress": pct,
                        "current_frame": frame_idx,
                        "total_frames": total_frames,
                        "fps": round(source_fps, 1),
                        "detections": total_detections_count,
                        "tracks": len(active_tracks),
                        "events": events_count,
                        "low_light": is_video_low_light,
                        "brightness": round(enh_meta.get("brightness", initial_avg_brightness), 1),
                        "raw_video_url": raw_video_url,
                        "enhanced_video_url": enhanced_video_url
                    }
                })

            # Commit batch every 3 sampled frames so DB remains in sync with real-time analysis
            if (frame_idx % (sample_step * 3)) == 0:
                db.commit()

        # Close enhanced video writer if open
        if enhanced_writer is not None:
            try:
                enhanced_writer.close()
            except Exception:
                pass
            enhanced_writer = None

        has_enhanced_file = (
            is_video_low_light and
            os.path.exists(enhanced_file_path) and
            os.path.getsize(enhanced_file_path) > 1000
        )
        final_enh_url = f"/storage/videos/{enhanced_filename}" if has_enhanced_file else None

        # Finalize successful analysis
        if video.status != "CANCELLED":
            video.status = "COMPLETED"
            video.is_low_light = is_video_low_light
            video.brightness = round(initial_avg_brightness, 1)
            video.enhanced_file_path = enhanced_file_path if has_enhanced_file else None
            db.commit()

            with _jobs_lock:
                job_data["status"] = "COMPLETED"
                job_data["progress"] = 100
                job_data["current_frame"] = total_frames
                job_data["low_light"] = is_video_low_light
                job_data["brightness"] = round(initial_avg_brightness, 1)
                job_data["raw_video_url"] = raw_video_url
                job_data["enhanced_video_url"] = final_enh_url

            manager.broadcast_sync({
                "type": "VIDEO_STATUS",
                "data": {
                    "video_id": video_id,
                    "status": "COMPLETED",
                    "progress": 100,
                    "detections": total_detections_count,
                    "tracks": len(active_tracks),
                    "events": events_count,
                    "low_light": is_video_low_light,
                    "brightness": round(initial_avg_brightness, 1),
                    "raw_video_url": raw_video_url,
                    "enhanced_video_url": final_enh_url
                }
            })

            logger.info(
                f"[VideoAI] Analysis SUCCESS for {video_id}: {total_detections_count} detections, "
                f"{len(active_tracks)} tracks, {events_count} alerts generated. Enhanced URL: {final_enh_url}"
            )


    except Exception as e:
        logger.error(f"[VideoAI] Error analyzing video {video_id}: {e}", exc_info=True)
        video.status = "ERROR"
        db.commit()
        with _jobs_lock:
            if video_id in _video_jobs:
                _video_jobs[video_id]["status"] = "ERROR"
                _video_jobs[video_id]["error"] = str(e)
        manager.broadcast_sync({
            "type": "VIDEO_STATUS",
            "data": {"video_id": video_id, "status": "ERROR", "error": str(e)}
        })
    finally:
        if enhanced_writer is not None:
            try:
                enhanced_writer.close()
            except Exception:
                pass
        if cap is not None:
            cap.release()
        db.close()


@router.get("/", response_model=List[VideoResponse])
def get_videos(db: Session = Depends(get_db)):
    videos = db.query(Video).order_by(Video.created_at.desc()).all()
    # Check disk for enhanced MP4s that exist and link them
    for v in videos:
        if not v.enhanced_file_path:
            candidate_enh = os.path.join(STORAGE_DIR, f"{v.id}_enhanced.mp4")
            if os.path.exists(candidate_enh) and os.path.getsize(candidate_enh) > 1000:
                v.enhanced_file_path = candidate_enh
                v.is_low_light = True
                db.commit()
    return videos


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: str, db: Session = Depends(get_db)):
    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Video not found")
    if not v.enhanced_file_path:
        candidate_enh = os.path.join(STORAGE_DIR, f"{v.id}_enhanced.mp4")
        if os.path.exists(candidate_enh) and os.path.getsize(candidate_enh) > 1000:
            v.enhanced_file_path = candidate_enh
            v.is_low_light = True
            db.commit()
    return v


@router.get("/{video_id}/analysis-status")
def get_video_analysis_status(video_id: str, db: Session = Depends(get_db)):
    """
    Real-time status endpoint reporting progress %, current_frame, total_frames,
    detections, tracks, and events for uploaded CCTV video processing.
    """
    with _jobs_lock:
        job = _video_jobs.get(video_id)
        if job:
            return job

    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Video not found")

    det_count = db.query(Detection).filter(Detection.video_id == video_id).count()
    enh_url = None
    if v.enhanced_file_path and os.path.exists(v.enhanced_file_path):
        enh_url = f"/storage/videos/{os.path.basename(v.enhanced_file_path)}"
    else:
        candidate_enh = os.path.join(STORAGE_DIR, f"{v.id}_enhanced.mp4")
        if os.path.exists(candidate_enh) and os.path.getsize(candidate_enh) > 1000:
            enh_url = f"/storage/videos/{v.id}_enhanced.mp4"
            v.enhanced_file_path = candidate_enh
            v.is_low_light = True
            db.commit()

    raw_url = f"/storage/videos/{os.path.basename(v.file_path)}" if v.file_path else None

    return {
        "video_id": v.id,
        "status": v.status,
        "progress": 100 if v.status == "COMPLETED" else 0,
        "current_frame": 0,
        "total_frames": 0,
        "fps": 25.0,
        "analysis_fps": 5.0,
        "duration": v.duration or 0.0,
        "detections": det_count,
        "tracks": 0,
        "events": 0,
        "low_light": bool(v.is_low_light),
        "brightness": v.brightness or 0.0,
        "raw_video_url": raw_url,
        "enhanced_video_url": enh_url,
        "error": None
    }


@router.post("/{video_id}/cancel")
def cancel_video_analysis(video_id: str, db: Session = Depends(get_db)):
    """Stop/cancel an in-progress background video analysis job."""
    with _jobs_lock:
        if video_id in _video_jobs:
            _video_jobs[video_id]["cancel_requested"] = True
            _video_jobs[video_id]["status"] = "CANCELLED"

    v = db.query(Video).filter(Video.id == video_id).first()
    if v and v.status in ["PROCESSING", "AI_ANALYZING"]:
        v.status = "CANCELLED"
        db.commit()

    return {"status": "ok", "video_id": video_id, "message": "Analysis cancelled"}


@router.post("/{video_id}/analyze")
def trigger_video_analysis(video_id: str, db: Session = Depends(get_db)):
    """Trigger real AI & ANPR analysis on an existing uploaded video."""
    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Video not found")
    if not os.path.exists(v.file_path):
        raise HTTPException(status_code=400, detail="Video file not found on disk")

    # Clear old detections & ANPR events for clean re-analysis
    db.query(Detection).filter(Detection.video_id == video_id).delete()
    db.query(ANPREvent).filter(ANPREvent.video_id == video_id).delete()
    db.query(Alert).filter(Alert.video_id == video_id).delete()
    v.status = "PROCESSING"
    db.commit()

    cap = cv2.VideoCapture(v.file_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    with _jobs_lock:
        _video_jobs[video_id] = {
            "video_id": video_id,
            "status": "PROCESSING",
            "progress": 0,
            "current_frame": 0,
            "total_frames": total_frames,
            "fps": round(fps, 1),
            "analysis_fps": 5.0,
            "duration": v.duration or 0.0,
            "detections": 0,
            "tracks": 0,
            "events": 0,
            "low_light": False,
            "brightness": 0.0,
            "raw_video_url": f"/storage/videos/{os.path.basename(v.file_path)}",
            "enhanced_video_url": None,
            "error": None,
            "cancel_requested": False
        }

    t = threading.Thread(
        target=run_video_inference_worker,
        args=(video_id, v.file_path, v.camera_id or "BOP-07"),
        daemon=True
    )
    t.start()
    return {"status": "started", "video_id": video_id}


@router.post("/upload", response_model=VideoResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    camera_id: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Accepts a video file from the Web Portal.
    Saves to storage/videos/ and creates a database record.
    Automatically launches the optimized YOLOv8 background worker.
    """
    video_id  = str(uuid.uuid4())
    filename  = f"{video_id}_{file.filename}"
    file_path = os.path.join(STORAGE_DIR, filename)

    # Stream file to disk
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail="Uploaded video file is empty (0 bytes).")

    assigned_camera = camera_id or "BOP-07"

    # Pre-open video to extract FPS, frame count, duration
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        cap.release()
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail="Invalid video file: OpenCV could not decode the video format or the file is corrupted.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if not fps or fps <= 0 or str(fps) == "nan":
        fps = 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail="Invalid video: contains 0 decodable video frames.")

    duration = round(total_frames / fps, 2) if fps > 0 else 0.0
    cap.release()

    video = Video(
        id         = video_id,
        filename   = file.filename,
        camera_id  = assigned_camera,
        status     = "PROCESSING",
        file_path  = file_path,
        file_size  = file_size,
        duration   = duration,
        created_at = datetime.utcnow(),
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    with _jobs_lock:
        _video_jobs[video_id] = {
            "video_id": video_id,
            "status": "PROCESSING",
            "progress": 0,
            "current_frame": 0,
            "total_frames": total_frames,
            "fps": round(fps, 1),
            "analysis_fps": 5.0,
            "duration": duration,
            "detections": 0,
            "tracks": 0,
            "events": 0,
            "low_light": False,
            "brightness": 0.0,
            "raw_video_url": f"/storage/videos/{filename}",
            "enhanced_video_url": None,
            "error": None,
            "cancel_requested": False
        }

    logger.info(f"[VIDEO UPLOAD] Successfully uploaded {file.filename} (ID: {video_id}, {file_size} bytes, {total_frames} frames @ {fps:.1f} FPS, duration: {duration}s)")

    # Run real YOLOv8 analysis in a background thread
    t = threading.Thread(
        target=run_video_inference_worker,
        args=(video_id, file_path, assigned_camera),
        daemon=True
    )
    t.start()
    logger.info(f"[VIDEO UPLOAD] Spawned background AI analysis worker for video {video_id}")

    return video


@router.patch("/{video_id}/status")
def update_video_status(video_id: str, status: str, db: Session = Depends(get_db)):
    """AI engine calls this to update processing status."""
    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Video not found")
    v.status = status
    db.commit()
    return {"status": "ok", "video_id": video_id, "new_status": status}

