from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from database.database import get_db, SessionLocal
from models.models import Video, Detection, Alert, Zone
from schemas.schemas import VideoResponse
from websocket.manager import manager
from datetime import datetime, timedelta
import uuid, os, shutil, threading, logging, sys, time, json
import cv2

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
            _shared_detector = Detector(model_path=model_path, conf_threshold=0.35)
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
    try:
        from shapely.geometry import Point
        from ai_engine.tracking.tracker import Tracker
        from ai_engine.intelligence.threat_engine import ThreatEngine

        detector = get_shared_detector()
        tracker = Tracker()

        # Look up optional zone explicitly configured for this specific video
        video_zone = db.query(Zone).filter(Zone.source_id == video_id, Zone.enabled == True).first()
        v_coords = None
        v_zone_name = None
        if video_zone and video_zone.coordinates_json:
            try:
                v_coords = json.loads(video_zone.coordinates_json)
                v_zone_name = video_zone.name
            except Exception as ze:
                logger.warning(f"[VideoAI] Failed to parse zone for video {video_id}: {ze}")

        # Load active watchlist records for face recognition and ANPR engine
        from routes.watchlist import _load_active_watchlist_records
        from ai_engine.intelligence.face_engine import get_face_engine
        from ai_engine.intelligence.anpr_engine import get_anpr_engine
        from ai_engine.night_vision import get_enhancer
        from ai_engine.evidence.recorder import get_evidence_recorder
        from models.models import ANPREvent, WatchlistPlate

        face_engine = get_face_engine()
        anpr_engine = get_anpr_engine()
        enhancer = get_enhancer()
        evidence_recorder = get_evidence_recorder()
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

        with _jobs_lock:
            job_data["total_frames"] = total_frames
            job_data["fps"] = round(source_fps, 1)
            job_data["analysis_fps"] = round(source_fps / sample_step, 1)
            job_data["duration"] = duration

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

            # Adaptive frame sampling: only run YOLO on sampled frames
            if (current_frame_idx % sample_step) != 0 and current_frame_idx != 0:
                continue

            # Ground-truth video-relative timeline timestamp (T+XX.Xs)
            video_time_sec = current_frame_idx / source_fps
            frame_timestamp = wall_start + timedelta(seconds=video_time_sec)

            # 1. Night Vision Pre-Inference Enhancement
            nv = enhancer.process(frame)
            enhanced_frame = nv.frame
            threat_engine.update_lighting(nv.lighting)

            # 2. Run real YOLOv8 inference on enhanced frame
            dets = detector.detect(enhanced_frame, camera_id=camera_id, track=True)

            # 3. Update persistent tracker
            active_tracks = tracker.update(dets)

            # 4. Save detection records with video timeline
            for track in active_tracks:
                bx, by = track.bottom_center
                is_in_zone = threat_engine.zone_polygon.contains(Point(bx, by)) if threat_engine.zone_polygon is not None else False

                event_type = "PERSON_DETECTED"
                face_match_data = None
                if track.object_type == "PERSON" and watchlist_records:
                    face_eval = face_engine.evaluate_person_track_face(
                        frame_bgr=enhanced_frame,
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
                            snap_path = evidence_recorder.record_alert_snapshot(
                                frame_bgr=enhanced_frame,
                                camera_id=camera_id,
                                event_type="WATCHLIST_MATCH",
                                threat_level=threat_lvl,
                                bbox=track.bbox,
                                lighting_profile=nv.lighting.profile,
                                frame_luminance=nv.lighting.luminance,
                                night_vision_applied=nv.applied,
                                timestamp=frame_timestamp,
                                object_label=f"{face_eval['person_name']} (Track #{track.track_id})",
                            )
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
                                snapshot_path=snap_path,
                                created_at=frame_timestamp,
                                updated_at=frame_timestamp,
                            )
                            db.add(alert_rec)

                if is_in_zone and threat_engine.zone_name:
                    event_type = "ZONE_INTRUSION"
                plate_info = None
                if track.object_type == "VEHICLE":
                    plate_eval = anpr_engine.evaluate_vehicle_plate(
                        frame_bgr=enhanced_frame,
                        vehicle_bbox=track.bbox,
                        camera_id=camera_id,
                        track_id=track.track_id,
                        vehicle_type=track.object_label.split(" ")[0].upper() if " " in track.object_label else "CAR"
                    )
                    plate_info = plate_eval

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
                                snap_p = evidence_recorder.record_alert_snapshot(
                                    frame_bgr=enhanced_frame,
                                    camera_id=camera_id,
                                    event_type="WATCHLIST_PLATE_MATCH",
                                    threat_level=wl_plate.threat_priority or "HIGH",
                                    bbox=track.bbox,
                                    lighting_profile=nv.lighting.profile,
                                    frame_luminance=nv.lighting.luminance,
                                    night_vision_applied=nv.applied,
                                    timestamp=frame_timestamp,
                                    object_label=f"{track.object_label} (Plate: {p_text})",
                                )
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
                                    snapshot_path=snap_p,
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
                                }
                            })

                    # Handle UNREADABLE Plate candidate (honestly logged, zero hallucination)
                    elif p_status == "UNREADABLE":
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
                                }
                            })

                if is_in_zone and threat_engine.zone_name:
                    event_type = "ZONE_INTRUSION"
                elif plate_info and plate_info.get("plate_status") == "READABLE":
                    event_type = "PLATE_DETECTED"
                elif plate_info and plate_info.get("plate_status") == "UNREADABLE":
                    event_type = "UNREADABLE_PLATE"
                elif track.object_type == "VEHICLE":
                    event_type = "VEHICLE_DETECTED"

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
                    night_vision_applied  = nv.applied,
                    frame_luminance       = round(nv.lighting.luminance, 2),
                    lighting_profile      = nv.lighting.profile,
                )
                db.add(det_rec)
                total_detections_count += 1


                # Real Alert Generation upon Zone Intrusion
                if is_in_zone and threat_engine.zone_name and track.object_type in ["PERSON", "VEHICLE"]:
                    if track.track_id not in alerted_tracks:
                        alerted_tracks.add(track.track_id)
                        events_count += 1
                        alert_id_str = f"ALERT-{frame_timestamp.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
                        threat_lvl = "HIGH" if track.object_type == "PERSON" else "CRITICAL"
                        snap_p = evidence_recorder.record_alert_snapshot(
                            frame_bgr=enhanced_frame,
                            camera_id=camera_id,
                            event_type="ZONE_INTRUSION",
                            threat_level=threat_lvl,
                            bbox=track.bbox,
                            lighting_profile=nv.lighting.profile,
                            frame_luminance=nv.lighting.luminance,
                            night_vision_applied=nv.applied,
                            timestamp=frame_timestamp,
                            object_label=track.object_label,
                        )
                        alert_rec = Alert(
                            id=str(uuid.uuid4()),
                            alert_id=alert_id_str,
                            camera_id=camera_id,
                            video_id=video_id,
                            event_type="ZONE_INTRUSION",
                            object_type=track.object_type,
                            object_id=track.object_label,
                            threat_level=threat_lvl,
                            reason=f"{track.object_label} entered {threat_engine.zone_name} in uploaded video at T+{video_time_sec:.1f}s.",
                            confidence=round(track.confidence, 1),
                            bbox_x=track.bbox.get("x", 0.0),
                            bbox_y=track.bbox.get("y", 0.0),
                            bbox_w=track.bbox.get("w", 0.0),
                            bbox_h=track.bbox.get("h", 0.0),
                            status="NEW",
                            snapshot_path=snap_p,
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
                        snap_p = evidence_recorder.record_alert_snapshot(
                            frame_bgr=enhanced_frame,
                            camera_id=camera_id,
                            event_type="LOITERING",
                            threat_level="CRITICAL",
                            bbox=track.bbox,
                            lighting_profile=nv.lighting.profile,
                            frame_luminance=nv.lighting.luminance,
                            night_vision_applied=nv.applied,
                            timestamp=frame_timestamp,
                            object_label=track.object_label,
                        )
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
                            snapshot_path=snap_p,
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

            # Broadcast WebSocket progress every 0.5 seconds
            now_ts = time.time()
            if (now_ts - last_ws_broadcast) >= 0.5:
                last_ws_broadcast = now_ts
                manager.broadcast_sync({
                    "type": "VIDEO_PROGRESS",
                    "data": {
                        "video_id": video_id,
                        "status": "AI_ANALYZING",
                        "progress": pct,
                        "current_frame": frame_idx,
                        "total_frames": total_frames,
                        "detections": total_detections_count,
                        "tracks": len(active_tracks),
                        "events": events_count
                    }
                })

            # Commit batch every 30 sampled frames
            if (frame_idx % (sample_step * 15)) == 0:
                db.commit()

        # Finalize successful analysis
        if video.status != "CANCELLED":
            db.commit()
            video.status = "COMPLETED"
            db.commit()

            with _jobs_lock:
                job_data["status"] = "COMPLETED"
                job_data["progress"] = 100
                job_data["current_frame"] = total_frames

            manager.broadcast_sync({
                "type": "VIDEO_STATUS",
                "data": {
                    "video_id": video_id,
                    "status": "COMPLETED",
                    "progress": 100,
                    "detections": total_detections_count,
                    "tracks": len(active_tracks),
                    "events": events_count
                }
            })

            logger.info(
                f"[VideoAI] Analysis SUCCESS for {video_id}: {total_detections_count} detections, "
                f"{len(active_tracks)} tracks, {events_count} alerts generated."
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
        if cap is not None:
            cap.release()
        db.close()


@router.get("/", response_model=List[VideoResponse])
def get_videos(db: Session = Depends(get_db)):
    return db.query(Video).order_by(Video.created_at.desc()).all()


@router.get("/{video_id}", response_model=VideoResponse)
def get_video(video_id: str, db: Session = Depends(get_db)):
    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Video not found")
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
    assigned_camera = camera_id or "BOP-07"

    # Pre-open video to extract FPS, frame count, duration
    cap = cv2.VideoCapture(file_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
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
            "error": None,
            "cancel_requested": False
        }

    # Run real YOLOv8 analysis in a background thread
    t = threading.Thread(
        target=run_video_inference_worker,
        args=(video_id, file_path, assigned_camera),
        daemon=True
    )
    t.start()

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

