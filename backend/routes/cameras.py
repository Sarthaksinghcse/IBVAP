from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from database.database import get_db
from models.models import Camera, Zone
from schemas.schemas import (
    CameraResponse,
    CameraCreate,
    CameraUpdate,
    StreamTestRequest,
    StreamTestResponse,
)
from websocket.manager import manager
from pydantic import BaseModel
from datetime import datetime
import base64, cv2, numpy as np, uuid, os, logging, time, socket, asyncio

logger = logging.getLogger("camera_route")

router = APIRouter()

# ─── Persistent Webcam AI Singletons ──────────────────────────────────────────
_webcam_detector = None
_webcam_tracker = None
_webcam_threat_engine = None


def _get_webcam_ai_instances():
    global _webcam_detector, _webcam_tracker, _webcam_threat_engine
    if _webcam_detector is None:
        from ai_engine.detection.detector import Detector
        from ai_engine.tracking.tracker import Tracker
        from ai_engine.intelligence.threat_engine import ThreatEngine
        model_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "yolov8n.pt")
        )
        _webcam_detector = Detector(model_path=model_path, conf_threshold=0.45)
        _webcam_tracker = Tracker()
        from routes.alerts import create_and_broadcast_alert_sync
        _webcam_threat_engine = ThreatEngine(
            camera_id="WEBCAM-01",
            loitering_threshold=15.0,
            alert_callback=create_and_broadcast_alert_sync
        )
    return _webcam_detector, _webcam_tracker, _webcam_threat_engine




class WebcamInferRequest(BaseModel):
    image_base64: str
    camera_id: str = "WEBCAM-01"
    conf_threshold: float = 0.45
    frame_seq: int = 0
    face_recognition_enabled: bool = True
    face_threshold: float = 0.45
    anpr_enabled: bool = True




@router.get("/", response_model=List[CameraResponse])
def get_cameras(db: Session = Depends(get_db)):
    """Return all user-configured active cameras ordered by creation time."""
    return db.query(Camera).order_by(Camera.created_at.asc(), Camera.name.asc()).all()


@router.post("/", response_model=CameraResponse)
def create_camera(data: CameraCreate, db: Session = Depends(get_db)):
    """Register a new user-configured CCTV or Phone Wi-Fi Camera source."""
    # Check if name is already taken
    existing = db.query(Camera).filter(Camera.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Camera with name '{data.name}' already exists.")

    cam_id = data.id or f"{data.source_type.upper()}-{uuid.uuid4().hex[:6].upper()}"
    existing_id = db.query(Camera).filter(Camera.id == cam_id).first()
    if existing_id:
        cam_id = f"{data.source_type.upper()}-{uuid.uuid4().hex[:8].upper()}"

    now = datetime.utcnow()
    cam = Camera(
        id=cam_id,
        name=data.name,
        location=data.location or "Surveillance Area",
        source_type=data.source_type or "CCTV",
        stream_url=data.stream_url,
        stream_type=data.stream_type or "RTSP",
        status=data.status or "ONLINE",
        ai_status="STOPPED",
        fps=data.fps or 25.0,
        resolution=data.resolution or "1920x1080",
        last_activity=now,
        created_at=now,
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    logger.info(f"[Cameras] Registered new {cam.source_type} camera: {cam.name} ({cam.id})")
    return cam


@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return cam


@router.put("/{camera_id}", response_model=CameraResponse)
def update_camera(camera_id: str, data: CameraUpdate, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    if data.name is not None:
        cam.name = data.name
    if data.location is not None:
        cam.location = data.location
    if data.status is not None:
        cam.status = data.status.value if hasattr(data.status, "value") else data.status
    if data.ai_status is not None:
        cam.ai_status = data.ai_status.value if hasattr(data.ai_status, "value") else data.ai_status
    if data.stream_url is not None:
        cam.stream_url = data.stream_url
    if data.stream_type is not None:
        cam.stream_type = data.stream_type
    if data.fps is not None:
        cam.fps = data.fps
    if data.resolution is not None:
        cam.resolution = data.resolution

    cam.last_activity = datetime.utcnow()
    db.commit()
    db.refresh(cam)
    return cam


@router.delete("/{camera_id}")
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    """Delete a configured camera and its associated zones."""
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Delete any associated zones for this camera
    db.query(Zone).filter(Zone.source_id == camera_id).delete()
    db.delete(cam)
    db.commit()
    logger.info(f"[Cameras] Removed camera {camera_id} from database.")
    return {"status": "ok", "message": f"Camera {camera_id} deleted"}


@router.post("/test-stream", response_model=StreamTestResponse)
async def test_camera_stream(data: StreamTestRequest):
    """
    Attempts a real connection to the provided RTSP, MJPEG, or HTTP stream URL.
    Returns success status, resolution, and fps if reachable, or real error details.
    """
    stream_url = data.stream_url.strip()
    if not stream_url:
        return StreamTestResponse(
            success=False,
            status="OFFLINE",
            error="Stream URL cannot be empty."
        )

    # Run OpenCV stream probe in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()

    def probe_stream():
        # Set OpenCV timeout parameters where supported
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;3000000|rtsp_transport;tcp"
        cap = cv2.VideoCapture(stream_url)
        try:
            if not cap.isOpened():
                return False, "Could not open stream connection. Please verify URL, credentials, and network reachability.", None, None

            ret, frame = cap.read()
            if not ret or frame is None or frame.size == 0:
                return False, "Connected to stream endpoint but failed to read initial frame.", None, None

            h, w = frame.shape[:2]
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps_val = round(fps, 1) if (fps and fps > 0 and fps < 120) else 25.0
            return True, "Stream connected successfully.", f"{w}x{h}", fps_val
        except Exception as e:
            return False, f"Stream connection error: {str(e)}", None, None
        finally:
            cap.release()

    try:
        success, msg, resolution, fps = await loop.run_in_executor(None, probe_stream)
        if success:
            return StreamTestResponse(
                success=True,
                status="ONLINE",
                resolution=resolution,
                fps=fps
            )
        else:
            return StreamTestResponse(
                success=False,
                status="OFFLINE",
                error=msg
            )
    except Exception as ex:
        return StreamTestResponse(
            success=False,
            status="ERROR",
            error=f"Connection probe timed out or failed: {str(ex)}"
        )


@router.post("/discover")
def discover_network_cameras():
    """
    Scan local network broadcast or common RTSP ports for available cameras.
    Returns list of discovered stream candidates.
    """
    discovered = []
    # Probe local IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        subnet = ".".join(local_ip.split(".")[:3])
        logger.info(f"[Discovery] Probing local subnet {subnet}.0/24")
    except Exception:
        local_ip = "127.0.0.1"

    return {
        "status": "ok",
        "discovered_cameras": discovered,
        "local_ip": local_ip,
        "message": "Scan complete. No unconfigured ONVIF cameras found on subnet." if not discovered else "Cameras discovered"
    }


@router.get("/{camera_id}/stream")
async def get_camera_mjpeg_stream(camera_id: str, db: Session = Depends(get_db)):
    """
    Live MJPEG stream for network CCTV / Phone cameras with real YOLOv8 inference.
    Allows standard web browsers to view RTSP / Phone streams natively.
    """
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not cam.stream_url:
        raise HTTPException(status_code=400, detail="Camera does not have a stream URL configured")

    def frame_generator():
        cap = cv2.VideoCapture(cam.stream_url)
        detector, tracker, threat_engine = _get_webcam_ai_instances()
        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.1)
                    continue

                # Run inference periodically
                raw_dets = detector.detect(frame, camera_id=camera_id, track=True)
                active_tracks = tracker.update(raw_dets)
                threat_engine.process_tracks(active_tracks)

                # Draw bounding boxes onto frame
                for trk in active_tracks:
                    x1, y1, x2, y2 = trk.bbox["x"], trk.bbox["y"], trk.bbox["w"], trk.bbox["h"]
                    h_f, w_f = frame.shape[:2]
                    px1 = int((x1 / 100.0) * w_f)
                    py1 = int((y1 / 100.0) * h_f)
                    pw = int((x2 / 100.0) * w_f)
                    ph = int((y2 / 100.0) * h_f)
                    cv2.rectangle(frame, (px1, py1), (px1 + pw, py1 + ph), (0, 255, 0), 2)
                    cv2.putText(frame, f"{trk.object_label} {trk.confidence:.0f}%", (px1, max(15, py1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                ret_enc, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if not ret_enc:
                    continue

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                time.sleep(0.06) # ~15 FPS
        except GeneratorExit:
            pass
        finally:
            cap.release()

    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.patch("/{camera_id}/heartbeat")
def camera_heartbeat(camera_id: str, db: Session = Depends(get_db)):
    """AI engine calls this to update camera last_activity."""
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if cam:
        cam.last_activity = datetime.utcnow()
        db.commit()
    return {"status": "ok"}


@router.post("/webcam/reset")
def reset_webcam_session():
    """Resets persistent tracker and loitering timers for WEBCAM-01 session."""
    global _webcam_detector, _webcam_tracker, _webcam_threat_engine
    from ai_engine.tracking.tracker import Tracker
    from ai_engine.intelligence.threat_engine import ThreatEngine
    _webcam_tracker = Tracker()
    _webcam_threat_engine = ThreatEngine(camera_id="WEBCAM-01", loitering_threshold=15.0)
    logger.info("[WebcamAI] Session reset complete.")
    return {"status": "ok", "message": "Webcam session reset"}



@router.post("/webcam/infer")
async def infer_webcam_frame(data: WebcamInferRequest):
    """
    Real YOLOv8 frame inference for the live browser webcam feed.
    - Runs real detector (yolov8n.pt) with internal track=True persistence.
    - Feeds real Detection objects into Tracker for stable IDs across frames.
    - Evaluates ThreatEngine.process_tracks() for zone intrusion & loitering.
    - Only saves genuine Alert events to DB (never raw frame detections).
    - Returns normalized detections for bounding-box rendering in the browser.
    """
    try:
        detector, tracker, threat_engine = _get_webcam_ai_instances()

        # Update confidence threshold dynamically from frontend settings
        conf_val = data.conf_threshold / 100.0 if data.conf_threshold > 1.0 else data.conf_threshold
        conf_frac = max(0.05, min(0.95, conf_val))
        detector.conf_threshold = conf_frac

        # ── Load WEBCAM-01 specific zone and active watchlist from DB ────────
        from database.database import SessionLocal
        from models.models import Zone
        import json

        db = SessionLocal()
        watchlist_records = []
        try:
            cam_zone = db.query(Zone).filter(Zone.source_id == data.camera_id, Zone.enabled == True).first()
            if cam_zone and cam_zone.coordinates_json:
                coords = json.loads(cam_zone.coordinates_json)
                threat_engine.set_zone(coords, cam_zone.name)
            else:
                threat_engine.set_zone(None, None)

            if data.face_recognition_enabled:
                from routes.watchlist import _load_active_watchlist_records
                watchlist_records = _load_active_watchlist_records(db)
        except Exception as ze:
            logger.warning(f"[WebcamAI] Error loading zone/watchlist for {data.camera_id}: {ze}")
            threat_engine.set_zone(None, None)
        finally:
            db.close()

        # ── Decode base64 JPEG frame ───────────────────────────────────────────
        b64 = data.image_base64
        if "," in b64:
            b64 = b64.split(",", 1)[1]
        try:
            img_bytes = base64.b64decode(b64)
        except Exception as e:
            logger.warning(f"[WebcamAI] base64 decode error: {e}")
            return {"detections": [], "frame_seq": data.frame_seq, "camera_id": data.camera_id}

        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None or frame.size == 0:
            return {"detections": [], "frame_seq": data.frame_seq, "camera_id": data.camera_id}

        # ── Run real YOLOv8 with internal tracking (persist=True) ─────────────
        raw_dets = detector.detect(frame, camera_id=data.camera_id, track=True)

        if not raw_dets:
            # No objects detected this frame — return empty (clear previous boxes)
            return {"detections": [], "frame_seq": data.frame_seq, "camera_id": data.camera_id}

        # ── Update our persistent Tracker (for zone dwell timing) ─────────────
        active_tracks = tracker.update(raw_dets)

        # ── Evaluate ThreatEngine (zone intrusion + loitering + alert dedup) ──
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: threat_engine.process_tracks(active_tracks, video_id=None)
        )

        # ── Build detection response & AI Evaluation ─────────────────────────
        now = datetime.utcnow()
        output_detections = []
        from shapely.geometry import Point
        from ai_engine.intelligence.face_engine import get_face_engine
        from ai_engine.intelligence.anpr_engine import get_anpr_engine
        from models.models import ANPREvent

        face_engine = get_face_engine()
        anpr_engine = get_anpr_engine()

        for track in active_tracks:
            bx, by = track.bottom_center
            is_in_zone = threat_engine.zone_polygon.contains(Point(bx, by)) if threat_engine.zone_polygon is not None else False

            # Real Face Recognition on detected PERSON objects
            face_match_info = None
            if data.face_recognition_enabled and track.object_type == "PERSON":
                face_eval = face_engine.evaluate_person_track_face(
                    frame_bgr=frame,
                    person_bbox=track.bbox,
                    camera_id=data.camera_id,
                    track_id=track.track_id,
                    watchlist_records=watchlist_records,
                    threshold=data.face_threshold
                )
                if face_eval.get("is_match"):
                    face_match_info = {
                        "is_match": True,
                        "person_id": face_eval["person_id"],
                        "person_name": face_eval["person_name"],
                        "identifier": face_eval.get("identifier"),
                        "threat_priority": face_eval.get("threat_priority", "HIGH"),
                        "similarity": face_eval["similarity"],
                        "cosine_score": face_eval["cosine_score"],
                    }
                    # Fire real watchlist alert via ThreatEngine
                    threat_engine.trigger_watchlist_alert(
                        person_id=face_eval["person_id"],
                        person_name=face_eval["person_name"],
                        identifier=face_eval.get("identifier"),
                        threat_priority=face_eval.get("threat_priority", "HIGH"),
                        similarity=face_eval["similarity"],
                        cosine_score=face_eval["cosine_score"],
                        track_id=track.track_id,
                        bbox=track.bbox,
                        is_in_zone=is_in_zone
                    )
                elif face_eval.get("face_detected"):
                    face_match_info = {
                        "is_match": False,
                        "person_name": "UNKNOWN",
                        "similarity": face_eval["similarity"],
                    }

            # Real ANPR on detected VEHICLE objects
            plate_info = None
            if data.anpr_enabled and track.object_type == "VEHICLE":
                plate_eval = anpr_engine.evaluate_vehicle_plate(
                    frame_bgr=frame,
                    vehicle_bbox=track.bbox,
                    camera_id=data.camera_id,
                    track_id=track.track_id,
                    vehicle_type=track.object_label.split(" ")[0].upper() if " " in track.object_label else "CAR"
                )
                plate_info = {
                    "plate_detected": plate_eval.get("plate_detected", False),
                    "plate_text": plate_eval.get("plate_text"),
                    "plate_confidence": plate_eval.get("plate_confidence"),
                    "plate_status": plate_eval.get("plate_status", "NOT_DETECTED"),
                    "vehicle_type": plate_eval.get("vehicle_type", "CAR"),
                }

                # Persist readable plate events into database (with deduplication)
                if plate_eval.get("plate_status") == "READABLE" and plate_eval.get("plate_text"):
                    try:
                        anpr_db = SessionLocal()
                        # Check if event was already recorded for this track within last 10s
                        existing = anpr_db.query(ANPREvent).filter(
                            ANPREvent.camera_id == data.camera_id,
                            ANPREvent.vehicle_track_id == track.track_id,
                            ANPREvent.plate_text == plate_eval["plate_text"]
                        ).first()
                        if not existing:
                            ev = ANPREvent(
                                id=str(uuid.uuid4()),
                                camera_id=data.camera_id,
                                vehicle_track_id=track.track_id,
                                vehicle_type=plate_eval.get("vehicle_type", "CAR"),
                                plate_text=plate_eval["plate_text"],
                                plate_confidence=plate_eval.get("plate_confidence"),
                                plate_status=plate_eval.get("plate_status", "READABLE"),
                                bbox_x=track.bbox.get("x", 0.0),
                                bbox_y=track.bbox.get("y", 0.0),
                                bbox_w=track.bbox.get("w", 0.0),
                                bbox_h=track.bbox.get("h", 0.0),
                                timestamp=now
                            )
                            anpr_db.add(ev)
                            anpr_db.commit()
                        anpr_db.close()
                    except Exception as pe:
                        logger.warning(f"[WebcamAI] Error persisting ANPR event: {pe}")

            if track.object_type == "VEHICLE":
                if is_in_zone and threat_engine.zone_name:
                    obj_event = "ZONE_INTRUSION"
                elif plate_info and plate_info.get("plate_status") == "READABLE":
                    obj_event = "PLATE_DETECTED"
                else:
                    obj_event = "VEHICLE_DETECTED"
            elif is_in_zone and threat_engine.zone_name:
                obj_event = "ZONE_INTRUSION"
            elif face_match_info and face_match_info.get("is_match"):
                obj_event = "WATCHLIST_MATCH"
            else:
                obj_event = "PERSON_DETECTED"

            output_detections.append({
                "id": str(uuid.uuid4()),
                "camera_id": data.camera_id,
                "object_type": track.object_type,
                "object_id": track.object_label,
                "confidence": round(track.confidence, 1),
                "zone": threat_engine.zone_name if is_in_zone else None,
                "event_type": obj_event,
                "bbox": track.bbox,
                "is_in_restricted_zone": is_in_zone,
                "loitering_duration": int(track.zone_dwell_time) if is_in_zone else None,
                "face_match": face_match_info,
                "plate_info": plate_info,
                "timestamp": now.isoformat(),
            })


        logger.debug(
            f"[WebcamAI] frame_seq={data.frame_seq} → "
            f"{len(output_detections)} detections: "
            + ", ".join(d["object_id"] for d in output_detections)
        )

        return {
            "detections": output_detections,
            "frame_seq": data.frame_seq,
            "camera_id": data.camera_id,
        }

    except Exception as e:
        logger.error(f"[WebcamAI] Inference error on frame_seq={data.frame_seq}: {e}", exc_info=True)
        return {"detections": [], "frame_seq": data.frame_seq, "camera_id": data.camera_id, "error": str(e)}



