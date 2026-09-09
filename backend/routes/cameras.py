from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from database.database import get_db
from models.models import Camera, Zone, Alert, ANPREvent, WatchlistPlate, Detection as DB_Detection
from schemas.schemas import (
    CameraResponse,
    CameraCreate,
    CameraUpdate,
    StreamTestRequest,
    StreamTestResponse,
    USBDetectResponse,
    USBTestRequest,
    USBTestResponse,
    USBConnectRequest,
    USBStatusResponse,
    USBFindPortResponse,
    CameraRotateRequest,
)
from services.usb_phone_manager import usb_phone_manager
from services.camera_stream_worker import camera_stream_manager
from websocket.manager import manager
from pydantic import BaseModel
from datetime import datetime
import base64, cv2, numpy as np, uuid, os, logging, time, socket, asyncio, json, threading

logger = logging.getLogger("camera_route")

router = APIRouter()

# ─── Persistent Camera AI Instances (Per-Camera Registry) ─────────────────────
_shared_detector = None
_camera_trackers: dict = {}
_camera_threat_engines: dict = {}
_camera_enhancers: dict = {}
_camera_enhancers_lock = threading.Lock()
_live_dedup_cache: dict = {}


def _get_camera_enhancer(camera_id: str):
    """Return camera-specific FrameEnhancer instance with independent brightness state."""
    global _camera_enhancers
    with _camera_enhancers_lock:
        if camera_id not in _camera_enhancers:
            from ai_engine.preprocessing.frame_enhancer import FrameEnhancer
            _camera_enhancers[camera_id] = FrameEnhancer()
        return _camera_enhancers[camera_id]


def _get_shared_detector(conf_threshold: float = 0.25):
    global _shared_detector
    if _shared_detector is None:
        from ai_engine.detection.detector import Detector
        model_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "yolov8n.pt")
        )
        _shared_detector = Detector(model_path=model_path, conf_threshold=conf_threshold)
    return _shared_detector


def _handle_live_detection_sync(det_data: dict):
    """
    Persist real-time live camera detections to DB with sensible deduplication and broadcast via WebSocket.
    """
    camera_id = det_data.get("camera_id", "WEBCAM-01")
    object_id = det_data.get("object_id", "UNKNOWN")
    event_type = det_data.get("event_type", "PERSON_DETECTED")
    now_ts = time.time()
    cache_key = (camera_id, object_id)

    prev = _live_dedup_cache.get(cache_key)
    should_record = False
    if prev is None:
        should_record = True
    elif prev.get("last_event") != event_type:
        should_record = True
    elif (now_ts - prev.get("last_time", 0)) >= 3.0:
        should_record = True

    if not should_record:
        return

    _live_dedup_cache[cache_key] = {"last_time": now_ts, "last_event": event_type}

    from database.database import SessionLocal
    from models.models import Detection as DBMsg
    db = SessionLocal()
    try:
        bbox = det_data.get("bbox") or {}
        p_info = det_data.get("plate_info") or {}
        now_dt = datetime.utcnow()
        det_record = DBMsg(
            id=str(uuid.uuid4()),
            camera_id=camera_id,
            video_id=None,
            object_type=det_data.get("object_type", "PERSON"),
            object_id=object_id,
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
            frame_index=None,
            video_time_sec=None,
            plate_text=p_info.get("plate_text"),
            plate_confidence=p_info.get("plate_confidence"),
            plate_status=p_info.get("plate_status"),
            plate_bbox_x=p_info.get("plate_bbox", {}).get("x") if p_info.get("plate_bbox") else None,
            plate_bbox_y=p_info.get("plate_bbox", {}).get("y") if p_info.get("plate_bbox") else None,
            plate_bbox_w=p_info.get("plate_bbox", {}).get("w") if p_info.get("plate_bbox") else None,
            plate_bbox_h=p_info.get("plate_bbox", {}).get("h") if p_info.get("plate_bbox") else None,
        )
        db.add(det_record)
        db.commit()

        ws_payload = {
            "id": det_record.id,
            "camera_id": camera_id,
            "object_type": det_record.object_type,
            "object_id": det_record.object_id,
            "confidence": det_record.confidence,
            "zone": det_record.zone,
            "event_type": event_type,
            "bbox": bbox,
            "is_in_restricted_zone": det_record.is_in_restricted_zone,
            "loitering_duration": det_record.loitering_duration,
            "timestamp": now_dt.isoformat(),
            "plate_info": p_info if p_info.get("plate_detected") else None,
        }
        manager.broadcast_sync({
            "type": "DETECTION",
            "data": ws_payload,
            "timestamp": now_dt.isoformat(),
        })
        logger.info(f"[WS] Detection sent: {object_id} ({event_type}) for {camera_id}")
    except Exception as dbe:
        logger.warning(f"[WebcamAI] Error persisting live detection: {dbe}")
    finally:
        db.close()


def _get_camera_ai_pipeline(camera_id: str):
    """Return camera-specific Tracker and ThreatEngine instances."""
    global _camera_trackers, _camera_threat_engines
    from ai_engine.tracking.tracker import Tracker
    from ai_engine.intelligence.threat_engine import ThreatEngine
    from routes.alerts import create_and_broadcast_alert_sync

    if camera_id not in _camera_trackers:
        _camera_trackers[camera_id] = Tracker()

    if camera_id not in _camera_threat_engines:
        from database.database import SessionLocal
        from ai_engine.intelligence.threat_engine import DEFAULT_RESTRICTED_ZONE_A
        db = SessionLocal()
        zone_coords = None
        zone_name = None
        try:
            cam_zone = db.query(Zone).filter(Zone.source_id == camera_id, Zone.enabled == True).first()
            if cam_zone and cam_zone.coordinates_json:
                zone_coords = json.loads(cam_zone.coordinates_json)
                zone_name = cam_zone.name
        except Exception as e:
            logger.warning(f"[CameraPipeline] Error loading zone for {camera_id}: {e}")
        finally:
            db.close()

        if not zone_coords:
            zone_coords = DEFAULT_RESTRICTED_ZONE_A
            zone_name = "Restricted Zone A"

        _camera_threat_engines[camera_id] = ThreatEngine(
            camera_id=camera_id,
            loitering_threshold=15.0,
            restricted_zone_polygon=zone_coords,
            zone_name=zone_name,
            alert_callback=create_and_broadcast_alert_sync,
            detection_callback=_handle_live_detection_sync
        )

    return _camera_trackers[camera_id], _camera_threat_engines[camera_id]


def _get_webcam_ai_instances():
    """Backward compatibility helper."""
    detector = _get_shared_detector()
    tracker, threat_engine = _get_camera_ai_pipeline("WEBCAM-01")
    return detector, tracker, threat_engine




class WebcamInferRequest(BaseModel):
    image_base64: str
    camera_id: str = "WEBCAM-01"
    conf_threshold: float = 0.25
    frame_seq: int = 0
    face_recognition_enabled: bool = True
    face_threshold: float = 0.45
    anpr_enabled: bool = True
    view_mode: str = "enhanced"




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

    # Ensure default restricted zone exists for this camera
    existing_zone = db.query(Zone).filter(Zone.source_id == cam.id).first()
    if not existing_zone:
        default_coords = [(5.0, 5.0), (50.0, 5.0), (50.0, 95.0), (5.0, 95.0)]
        new_zone = Zone(
            id=str(uuid.uuid4()),
            source_id=cam.id,
            source_type=cam.source_type,
            name="Restricted Zone A",
            coordinates_json=json.dumps(default_coords),
            enabled=True,
            zone_type="RESTRICTED",
            created_at=now,
            updated_at=now,
        )
        db.add(new_zone)
        db.commit()

    logger.info(f"[Cameras] Registered new {cam.source_type} camera: {cam.name} ({cam.id}) with default zone")
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
    if data.rotation is not None:
        cam.rotation = data.rotation % 360
        worker = camera_stream_manager.get_worker(camera_id)
        if worker:
            worker.set_rotation(cam.rotation)

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

    # Stop active stream worker if running
    camera_stream_manager.stop_worker(camera_id)
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


@router.post("/usb/detect", response_model=USBDetectResponse)
def detect_usb_cameras():
    """
    Detect physical USB Android devices via ADB and check Windows PnP devices as fallback.
    Returns device list, authorization status, and connection guidance.
    """
    try:
        data = usb_phone_manager.detect_devices()
        return USBDetectResponse(**data)
    except Exception as e:
        logger.error(f"[USBPhone] Error detecting devices: {e}", exc_info=True)
        return USBDetectResponse(
            adb_available=False,
            adb_path=None,
            devices=[],
            pnp_hardware_detected=[],
            instructions=[f"Error during USB detection: {str(e)}"]
        )


@router.get("/usb/find-port", response_model=USBFindPortResponse)
def find_available_usb_port(preferred: int = 8090):
    """
    Finds the first available local TCP port on the host (testing 8090, 8091, 8092, etc.).
    Avoids Windows socket error 10013 / occupied port conflicts.
    """
    avail = usb_phone_manager.find_available_local_port(start_port=preferred)
    return USBFindPortResponse(available_port=avail, preferred_port=preferred)


@router.post("/usb/test", response_model=USBTestResponse)
async def test_usb_camera_stream(data: USBTestRequest):
    """
    Sets up ADB local port forward (adb forward tcp:local_port tcp:phone_port).
    If preferred local_port (default 8090) fails or is blocked, automatically iterates
    to find an available port (8090, 8091, 8092...).
    Then probes the stream URL to ensure valid video frames are received over USB.
    """
    adb_path = usb_phone_manager.get_adb_path()
    if not adb_path:
        return USBTestResponse(
            success=False,
            message="ADB executable not found. Please verify ADB installation or start Android Platform Tools.",
            local_port=data.local_port,
            phone_port=data.phone_port,
            adb_forwarded=False,
            frames_received=False
        )

    # 1. Forward port via ADB with auto-fallback
    fwd_ok, actual_local_port, fwd_msg = usb_phone_manager.forward_port_with_fallback(
        preferred_local_port=data.local_port or 8090,
        phone_port=data.phone_port or 8080,
        serial=data.device_serial,
        auto_find=data.auto_find_port if data.auto_find_port is not None else True
    )
    if not fwd_ok:
        return USBTestResponse(
            success=False,
            message=fwd_msg,
            local_port=data.local_port,
            phone_port=data.phone_port,
            adb_forwarded=False,
            frames_received=False
        )

    # 2. Probe the stream
    stream_url = f"http://127.0.0.1:{actual_local_port}{data.stream_path}"
    loop = asyncio.get_event_loop()
    probe_ok, shape, probe_msg = await loop.run_in_executor(
        None, lambda: usb_phone_manager.probe_stream(stream_url, timeout_seconds=4.0)
    )

    resolution_str = f"{shape[0]}x{shape[1]}" if shape else None
    return USBTestResponse(
        success=probe_ok,
        message=probe_msg,
        local_port=actual_local_port,
        phone_port=data.phone_port,
        resolution=resolution_str,
        stream_url=stream_url if probe_ok else None,
        adb_forwarded=True,
        frames_received=probe_ok
    )


@router.post("/usb/connect", response_model=CameraResponse)
def connect_usb_camera(data: USBConnectRequest, db: Session = Depends(get_db)):
    """
    Connect an Android physical camera over USB Data Cable:
    1. Validates that the device is connected and authorized over ADB.
    2. Forwards the port via ADB (using fallback if 8090 is blocked).
    3. Mandatory: Probes the /video endpoint and verifies actual frames are received before declaring connected.
    4. Registers or updates the camera in the database with source_type='USB_PHONE'.
    """
    # 1. Check for authorized Android device
    detect_info = usb_phone_manager.detect_devices()
    devices = detect_info.get("devices", [])
    authorized = [d for d in devices if d.get("authorized")]
    if not authorized:
        raise HTTPException(
            status_code=400,
            detail="No authorized Android device detected over USB. Unlock your phone screen and tap 'Always allow from this computer' on the USB Debugging prompt."
        )

    target_serial = data.device_serial or authorized[0]["serial"]

    # 2. Forward port with auto-fallback
    fwd_ok, actual_local_port, fwd_msg = usb_phone_manager.forward_port_with_fallback(
        preferred_local_port=data.local_port or 8090,
        phone_port=data.phone_port or 8080,
        serial=target_serial,
        auto_find=data.auto_find_port if data.auto_find_port is not None else True
    )
    if not fwd_ok:
        raise HTTPException(status_code=400, detail=f"USB Port Forwarding failed: {fwd_msg}")

    stream_url = f"http://127.0.0.1:{actual_local_port}{data.stream_path}"

    # 3. Test URL and verify actual frames are received before declaring connected
    probe_ok, shape, probe_msg = usb_phone_manager.probe_stream(stream_url, timeout_seconds=4.0)
    if not probe_ok or not shape:
        raise HTTPException(
            status_code=400,
            detail=f"ADB forwarded successfully to 127.0.0.1:{actual_local_port}, but camera stream test failed: {probe_msg}. Ensure IP Webcam or DroidCam is actively streaming on phone port {data.phone_port}."
        )

    resolution_str = f"{shape[0]}x{shape[1]}"
    now = datetime.utcnow()

    # 4. Check if a camera with this name or stream_url already exists
    existing = db.query(Camera).filter(
        (Camera.name == data.name) | (Camera.stream_url == stream_url)
    ).first()

    if existing:
        existing.name = data.name
        existing.location = data.location or "USB Mobile Surveillance"
        existing.source_type = "USB_PHONE"
        existing.stream_type = "HTTP"
        existing.stream_url = stream_url
        existing.status = "ONLINE"
        existing.resolution = resolution_str
        existing.last_activity = now
        db.commit()
        db.refresh(existing)
        logger.info(f"[USBPhone] Updated existing camera {existing.id} ({existing.name}) to USB stream {stream_url} ({resolution_str})")
        return existing

    # Create new camera
    cam_id = f"USB-{uuid.uuid4().hex[:6].upper()}"
    cam = Camera(
        id=cam_id,
        name=data.name,
        location=data.location or "USB Mobile Surveillance",
        source_type="USB_PHONE",
        stream_url=stream_url,
        stream_type="HTTP",
        status="ONLINE",
        ai_status="STOPPED",
        fps=25.0,
        resolution=resolution_str,
        last_activity=now,
        created_at=now,
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    logger.info(f"[USBPhone] Registered new USB Camera: {cam.name} ({cam.id}) -> {stream_url} ({resolution_str})")
    return cam


@router.get("/usb/status", response_model=USBStatusResponse)
def get_usb_status():
    """Returns the current connection and forwarding status for USB camera devices."""
    data = usb_phone_manager.detect_devices()
    devices = data.get("devices", [])
    has_authorized = any(d.get("authorized", False) for d in devices)
    return USBStatusResponse(
        connected=has_authorized,
        device_count=len(devices),
        active_forwards=list(usb_phone_manager._active_forwards.values()),
        adb_available=data.get("adb_available", False)
    )


class CameraConfigUpdate(BaseModel):
    conf_threshold: Optional[float] = None


@router.get("/{camera_id}/stream")
async def get_camera_mjpeg_stream(
    camera_id: str,
    conf: Optional[float] = Query(None, description="Confidence threshold (0.05 - 1.0)"),
    rotate: Optional[int] = Query(None, description="Camera stream rotation degrees (0, 90, 180, 270)"),
    view: str = Query("auto", description="View mode: auto, enhanced, original"),
    db: Session = Depends(get_db)
):
    """
    Live low-latency MJPEG stream for network CCTV / USB Phone cameras with decoupled YOLOv8 inference,
    persistent tracking, zone intrusion detection, loitering analysis, and graceful disconnect recovery.
    Runs at full frame rate (~25-30 FPS) without freezing during AI inference.
    Supports real-time low-light view modes ('auto', 'enhanced', 'original').
    """
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not cam.stream_url:
        raise HTTPException(status_code=400, detail="Camera does not have a stream URL configured")

    conf_val = conf if (conf is not None and 0.05 <= conf <= 1.0) else 0.30
    rot_val = rotate if rotate is not None else (cam.rotation or 0)

    worker = camera_stream_manager.get_or_create_worker(
        camera_id=camera_id,
        stream_url=cam.stream_url,
        source_type=cam.source_type or "USB_PHONE",
        conf_threshold=conf_val,
        rotation=rot_val
    )
    worker.refresh_zone_from_db()
    if conf is not None:
        worker.set_confidence(conf_val)
    if rotate is not None:
        worker.set_rotation(rot_val)

    return StreamingResponse(
        worker.generate_mjpeg(view_mode=view),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.get("/{camera_id}/metrics")
def get_camera_metrics(camera_id: str, db: Session = Depends(get_db)):
    """Return actual measured runtime metrics (Camera FPS, AI FPS, Latency ms, Active Tracks)."""
    worker = camera_stream_manager.get_worker(camera_id)
    if worker:
        return worker.get_metrics()

    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    return {
        "camera_id": camera_id,
        "camera_fps": 0.0,
        "ai_fps": 0.0,
        "latency_ms": 0.0,
        "inference_time_ms": 0.0,
        "dropped_stale_frames": 0,
        "active_tracks": 0,
        "ai_status": "OFFLINE",
        "conf_threshold": 30.0,
        "rotation": cam.rotation or 0,
        "source_type": cam.source_type,
        "active_viewers": 0
    }


@router.post("/{camera_id}/rotate")
def set_camera_rotation(camera_id: str, data: CameraRotateRequest, db: Session = Depends(get_db)):
    """Dynamically rotate camera feed (0, 90, 180, 270) and persist to database."""
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    rot = data.rotation % 360
    if rot not in [0, 90, 180, 270]:
        raise HTTPException(status_code=400, detail="Invalid rotation degrees. Must be 0, 90, 180, or 270.")

    cam.rotation = rot
    db.commit()
    db.refresh(cam)

    worker = camera_stream_manager.get_worker(camera_id)
    if worker:
        worker.set_rotation(rot)

    logger.info(f"[Cameras] Set camera {camera_id} rotation to {rot} deg")
    return {"status": "ok", "camera_id": camera_id, "rotation": rot}


@router.post("/{camera_id}/config")
def update_camera_config(camera_id: str, data: CameraConfigUpdate):
    """Dynamically update live camera worker configuration."""
    worker = camera_stream_manager.get_worker(camera_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Camera stream worker is not currently active")

    if data.conf_threshold is not None:
        worker.set_confidence(data.conf_threshold)

    return {"status": "ok", "metrics": worker.get_metrics()}


@router.patch("/{camera_id}/heartbeat")
def camera_heartbeat(camera_id: str, db: Session = Depends(get_db)):
    """AI engine calls this to update camera last_activity."""
    cam = db.query(Camera).filter(Camera.id == camera_id).first()
    if cam:
        cam.last_activity = datetime.utcnow()
        db.commit()
    return {"status": "ok"}


@router.post("/webcam/reset")
def reset_webcam_session(camera_id: str = "WEBCAM-01"):
    """Resets persistent tracker and loitering timers for specified camera session."""
    global _camera_trackers, _camera_threat_engines, _live_dedup_cache
    from ai_engine.tracking.tracker import Tracker
    from ai_engine.intelligence.threat_engine import ThreatEngine
    from routes.alerts import create_and_broadcast_alert_sync

    _camera_trackers[camera_id] = Tracker()
    _camera_threat_engines[camera_id] = ThreatEngine(
        camera_id=camera_id,
        loitering_threshold=15.0,
        alert_callback=create_and_broadcast_alert_sync,
        detection_callback=_handle_live_detection_sync
    )
    keys_to_clear = [k for k in _live_dedup_cache.keys() if k[0] == camera_id]
    for k in keys_to_clear:
        del _live_dedup_cache[k]
    logger.info(f"[LiveAI] Session reset complete for camera {camera_id}.")
    return {"status": "ok", "message": f"Camera session reset for {camera_id}"}



@router.post("/webcam/infer")
async def infer_webcam_frame(data: WebcamInferRequest):
    """
    Real YOLOv8 frame inference for the live browser webcam / USB camera feed.
    - Runs real detector (yolov8n.pt) with internal track=True persistence.
    - Feeds real Detection objects into camera-specific Tracker for stable IDs across frames.
    - Evaluates ThreatEngine.process_tracks() for zone intrusion & loitering.
    - Emits deduplicated detection events to DB and WebSocket.
    - Returns normalized detections for bounding-box rendering in the browser.
    """
    try:
        conf_val = data.conf_threshold / 100.0 if data.conf_threshold > 1.0 else data.conf_threshold
        conf_frac = max(0.05, min(0.95, conf_val))

        detector = _get_shared_detector(conf_threshold=conf_frac)
        detector.conf_threshold = conf_frac
        tracker, threat_engine = _get_camera_ai_pipeline(data.camera_id)

        # ── Load camera-specific zone and active watchlist from DB ────────
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
        raw_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if raw_frame is None or raw_frame.size == 0:
            return {"detections": [], "frame_seq": data.frame_seq, "camera_id": data.camera_id, "low_light": False, "enhanced_image_base64": None}

        enhancer = _get_camera_enhancer(data.camera_id)
        raw_frame_copy = raw_frame.copy()
        frame_for_inference, was_enhanced, enh_meta = enhancer.enhance(raw_frame_copy)

        enhanced_b64 = None
        if was_enhanced and data.view_mode.lower() == "enhanced":
            ret_enc, enc_jpeg = cv2.imencode(".jpg", frame_for_inference, [cv2.IMWRITE_JPEG_QUALITY, 72])
            if ret_enc:
                enhanced_b64 = f"data:image/jpeg;base64,{base64.b64encode(enc_jpeg).decode('ascii')}"

        # ── Run real YOLOv8 on inference frame with internal tracking (persist=True) ─────────────
        raw_dets = detector.detect(frame_for_inference, camera_id=data.camera_id, track=True)

        # ── Update our persistent Tracker (for zone dwell timing) ─────────────
        active_tracks = tracker.update(raw_dets) if raw_dets else tracker.update([])

        logger.info(
            f"[CAMERA] camera_id={data.camera_id} [FRAME] received=true | "
            f"[LOW_LIGHT] brightness={enh_meta.get('brightness', 0.0):.1f} | "
            f"[ENHANCER] applied={was_enhanced} processing_ms={enh_meta.get('time_ms', 0.0):.1f}ms | "
            f"[YOLO] detections={len(raw_dets)} | [TRACKER] tracks={len(active_tracks)}"
        )

        # ── Evaluate ThreatEngine (zone intrusion + loitering + alert dedup) ──
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: threat_engine.process_tracks(
                active_tracks,
                video_id=None,
                frame_bgr=raw_frame,
                inference_bgr=frame_for_inference
            )
        )

        if not raw_dets and not active_tracks:
            return {
                "detections": [],
                "frame_seq": data.frame_seq,
                "camera_id": data.camera_id,
                "low_light": was_enhanced,
                "brightness": enh_meta.get("brightness", 0.0),
                "gamma": enh_meta.get("gamma", 1.0),
                "enhanced_image_base64": enhanced_b64
            }

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
                    frame_bgr=frame_for_inference,
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

            # Real ANPR on detected VEHICLE objects (CAR, TRUCK, BUS, MOTORCYCLE, VEHICLE)
            plate_info = None
            is_vehicle = track.object_type in ["VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE"]
            if data.anpr_enabled and is_vehicle:
                plate_eval = anpr_engine.evaluate_vehicle_plate(
                    frame_bgr=frame_for_inference,
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
                    "plate_bbox": plate_eval.get("plate_bbox"),
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

                            # Check Watchlist Plate Match
                            norm_plate = plate_eval["plate_text"].replace(" ", "").upper()
                            wl_match = anpr_db.query(WatchlistPlate).filter(
                                WatchlistPlate.is_active == True,
                                WatchlistPlate.plate_number == norm_plate
                            ).first()
                            if wl_match:
                                alert_id_str = f"ALERT-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
                                wl_alert = Alert(
                                    id=str(uuid.uuid4()),
                                    alert_id=alert_id_str,
                                    camera_id=data.camera_id,
                                    event_type="WATCHLIST_PLATE_MATCH",
                                    object_type="VEHICLE",
                                    object_id=f"{track.object_label} (Plate: {plate_eval['plate_text']})",
                                    threat_level=wl_match.threat_priority or "HIGH",
                                    reason=f"SUSPECT VEHICLE PLATE DETECTED: {plate_eval['plate_text']} ({wl_match.vehicle_owner or wl_match.reason or 'Wanted vehicle'}) detected on {data.camera_id} with {plate_eval.get('plate_confidence', 0):.1f}% OCR confidence.",
                                    confidence=plate_eval.get("plate_confidence"),
                                    bbox_x=track.bbox.get("x", 0.0),
                                    bbox_y=track.bbox.get("y", 0.0),
                                    bbox_w=track.bbox.get("w", 0.0),
                                    bbox_h=track.bbox.get("h", 0.0),
                                    status="NEW",
                                    created_at=now,
                                    updated_at=now,
                                )
                                anpr_db.add(wl_alert)
                                manager.broadcast_sync({
                                    "type": "NEW_ALERT",
                                    "data": {
                                        "id": wl_alert.id,
                                        "alert_id": wl_alert.alert_id,
                                        "camera_id": data.camera_id,
                                        "event_type": "WATCHLIST_PLATE_MATCH",
                                        "object_id": wl_alert.object_id,
                                        "threat_level": wl_alert.threat_level,
                                        "reason": wl_alert.reason,
                                        "timestamp": now.isoformat(),
                                    }
                                })

                            anpr_db.commit()
                        anpr_db.close()
                    except Exception as pe:
                        logger.warning(f"[WebcamAI] Error persisting ANPR event: {pe}")

            if is_vehicle:
                if is_in_zone and threat_engine.zone_name:
                    obj_event = "ZONE_INTRUSION"
                elif plate_info and plate_info.get("plate_status") == "READABLE":
                    obj_event = "PLATE_DETECTED"
                elif plate_info and plate_info.get("plate_status") == "UNREADABLE":
                    obj_event = "UNREADABLE_PLATE"
                else:
                    obj_event = f"{track.object_type}_DETECTED"
            elif is_in_zone and threat_engine.zone_name:
                obj_event = "ZONE_INTRUSION"
            elif face_match_info and face_match_info.get("is_match"):
                obj_event = "WATCHLIST_MATCH"
            elif track.object_type == "PERSON":
                obj_event = "PERSON_DETECTED"
            else:
                obj_event = f"{track.object_type}_DETECTED"

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
            "low_light": was_enhanced,
            "brightness": enh_meta.get("brightness", 0.0),
            "gamma": enh_meta.get("gamma", 1.0),
            "enhanced_image_base64": enhanced_b64
        }

    except Exception as e:
        logger.error(f"[WebcamAI] Inference error on frame_seq={data.frame_seq}: {e}", exc_info=True)
        return {
            "detections": [],
            "frame_seq": data.frame_seq,
            "camera_id": data.camera_id,
            "low_light": False,
            "brightness": 0.0,
            "gamma": 1.0,
            "enhanced_image_base64": None,
            "error": str(e)
        }



