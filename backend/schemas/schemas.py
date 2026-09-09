from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class ThreatLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    NONE     = "NONE"

class AlertStatus(str, Enum):
    NEW                  = "NEW"
    ACKNOWLEDGED         = "ACKNOWLEDGED"
    UNDER_INVESTIGATION  = "UNDER_INVESTIGATION"
    RESOLVED             = "RESOLVED"

class CameraStatus(str, Enum):
    ONLINE      = "ONLINE"
    OFFLINE     = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"
    ERROR       = "ERROR"

class CameraSourceType(str, Enum):
    CCTV      = "CCTV"
    PHONE     = "PHONE"
    WEBCAM    = "WEBCAM"
    USB_PHONE = "USB_PHONE"

class AIStatus(str, Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    ERROR   = "ERROR"

class VideoStatus(str, Enum):
    READY        = "READY"
    UPLOADING    = "UPLOADING"
    PROCESSING   = "PROCESSING"
    AI_ANALYZING = "AI_ANALYZING"
    COMPLETED    = "COMPLETED"
    CANCELLED    = "CANCELLED"
    ERROR        = "ERROR"


# ─── Shared Sub-Schemas ───────────────────────────────────────────────────────

class BBoxSchema(BaseModel):
    x: float
    y: float
    w: float
    h: float


# ─── Camera Schemas ───────────────────────────────────────────────────────────

class CameraCreate(BaseModel):
    id:          Optional[str] = None
    name:        str
    location:    Optional[str] = "Surveillance Area"
    source_type: Optional[str] = "CCTV"
    stream_url:  Optional[str] = None
    stream_type: Optional[str] = "RTSP"
    status:      Optional[CameraStatus] = CameraStatus.ONLINE
    resolution:  Optional[str] = "1920x1080"
    fps:         Optional[float] = 25.0
    rotation:    Optional[int] = 0

class CameraUpdate(BaseModel):
    name:        Optional[str] = None
    location:    Optional[str] = None
    status:      Optional[CameraStatus] = None
    ai_status:   Optional[AIStatus] = None
    stream_url:  Optional[str] = None
    stream_type: Optional[str] = None
    fps:         Optional[float] = None
    resolution:  Optional[str] = None
    rotation:    Optional[int] = None

class CameraRotateRequest(BaseModel):
    rotation: int = 0  # 0, 90, 180, 270

class StreamTestRequest(BaseModel):
    stream_url:  str
    stream_type: Optional[str] = "RTSP"

class StreamTestResponse(BaseModel):
    success:     bool
    status:      str
    resolution:  Optional[str] = None
    fps:         Optional[float] = None
    error:       Optional[str] = None

class CameraResponse(BaseModel):
    id:            str
    name:          str
    location:      str
    source_type:   Optional[str]   = "CCTV"
    stream_url:    Optional[str]   = None
    stream_type:   Optional[str]   = "RTSP"
    status:        CameraStatus
    ai_status:     AIStatus
    fps:           Optional[float] = 25.0
    resolution:    Optional[str]   = "1920x1080"
    rotation:      Optional[int]   = 0
    last_activity: datetime
    created_at:    Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─── USB Phone Camera Schemas ─────────────────────────────────────────────────

class USBDeviceItem(BaseModel):
    serial: str
    state: str
    model: str
    product: Optional[str] = ""
    usb_info: Optional[str] = ""
    authorized: bool = True

class USBHardwareItem(BaseModel):
    name: str
    instance_id: Optional[str] = ""
    status: Optional[str] = "OK"

class USBDetectResponse(BaseModel):
    adb_available: bool
    adb_path: Optional[str] = None
    devices: List[USBDeviceItem] = []
    pnp_hardware_detected: List[USBHardwareItem] = []
    instructions: List[str] = []

class USBTestRequest(BaseModel):
    phone_port: Optional[int] = 8080
    local_port: Optional[int] = 8090
    stream_path: Optional[str] = "/video"
    device_serial: Optional[str] = None
    auto_find_port: Optional[bool] = True

class USBTestResponse(BaseModel):
    success: bool
    message: str
    local_port: Optional[int] = 8090
    phone_port: Optional[int] = 8080
    resolution: Optional[str] = None
    stream_url: Optional[str] = None
    adb_forwarded: bool = False
    frames_received: bool = False

class USBConnectRequest(BaseModel):
    name: str
    location: Optional[str] = "USB Mobile Surveillance"
    device_serial: Optional[str] = None
    phone_port: Optional[int] = 8080
    local_port: Optional[int] = 8090
    stream_path: Optional[str] = "/video"
    app_type: Optional[str] = "IP_WEBCAM" # IP_WEBCAM | DROIDCAM | CUSTOM
    auto_find_port: Optional[bool] = True

class USBFindPortResponse(BaseModel):
    available_port: int
    preferred_port: int

class USBStatusResponse(BaseModel):
    connected: bool
    device_count: int
    active_forwards: List[dict] = []
    adb_available: bool



# ─── Video Schemas ────────────────────────────────────────────────────────────

class VideoResponse(BaseModel):
    id:         str
    filename:   str
    camera_id:  Optional[str]   = None
    status:     VideoStatus
    file_path:          Optional[str]   = None
    enhanced_file_path: Optional[str]   = None
    is_low_light:       Optional[bool]  = False
    brightness:         Optional[float] = None
    file_size:          Optional[int]   = None
    duration:           Optional[float] = None
    created_at:         datetime

    model_config = {"from_attributes": True}


# ─── Detection Schemas ────────────────────────────────────────────────────────

class PlateInfoSchema(BaseModel):
    plate_detected:   bool = False
    plate_text:       Optional[str] = None
    plate_confidence: Optional[float] = None
    plate_status:     str = "NOT_DETECTED" # READABLE | UNREADABLE | UNCERTAIN | NOT_DETECTED
    plate_bbox:       Optional[BBoxSchema] = None
    vehicle_type:     Optional[str] = None


class DetectionCreate(BaseModel):
    camera_id:             str
    video_id:              Optional[str]   = None
    object_type:           str
    object_id:             str
    confidence:            float           = Field(ge=0, le=100)
    zone:                  Optional[str]   = None
    event_type:            str
    bbox:                  BBoxSchema
    is_in_restricted_zone: Optional[bool]  = False
    loitering_duration:    Optional[int]   = None
    timestamp:             Optional[datetime] = None
    session_id:            Optional[str]   = None
    # Video-relative frame identity — populated only for uploaded-video detections
    frame_index:           Optional[int]   = None
    video_time_sec:        Optional[float] = None
    plate_info:            Optional[PlateInfoSchema] = None

class DetectionResponse(BaseModel):
    id:                    str
    camera_id:             str
    video_id:              Optional[str]   = None
    session_id:            Optional[str]   = None
    object_type:           str
    object_id:             str
    confidence:            float
    zone:                  Optional[str]   = None
    event_type:            str
    bbox:                  BBoxSchema
    is_in_restricted_zone: bool
    loitering_duration:    Optional[int]   = None
    timestamp:             datetime
    # Video-relative frame identity
    frame_index:           Optional[int]   = None
    video_time_sec:        Optional[float] = None
    plate_info:            Optional[PlateInfoSchema] = None

    model_config = {"from_attributes": True}


# ─── Watchlist Plate Schemas ──────────────────────────────────────────────────

class WatchlistPlateCreate(BaseModel):
    plate_number:    str
    vehicle_owner:   Optional[str] = None
    vehicle_model:   Optional[str] = None
    threat_priority: Optional[str] = "HIGH"
    reason:          Optional[str] = None

class WatchlistPlateResponse(BaseModel):
    id:              str
    plate_number:    str
    vehicle_owner:   Optional[str] = None
    vehicle_model:   Optional[str] = None
    threat_priority: str
    reason:          Optional[str] = None
    is_active:       bool
    created_at:      datetime

    model_config = {"from_attributes": True}


# ─── Alert Schemas ────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    camera_id:     str
    video_id:      Optional[str]   = None
    event_type:    str
    object_type:   str
    object_id:     str
    threat_level:  ThreatLevel
    reason:        str
    confidence:    Optional[float] = None
    bbox:          Optional[BBoxSchema] = None
    snapshot_path: Optional[str]   = None

class AlertUpdate(BaseModel):
    status: AlertStatus

class AlertResponse(BaseModel):
    id:            str
    alert_id:      str
    camera_id:     str
    video_id:      Optional[str]   = None
    event_type:    str
    object_type:   str
    object_id:     str
    threat_level:  ThreatLevel
    reason:        str
    confidence:    Optional[float] = None
    bbox:          Optional[BBoxSchema] = None
    status:        AlertStatus
    snapshot_path: Optional[str]   = None
    created_at:    datetime
    updated_at:    datetime

    model_config = {"from_attributes": True}



# ─── Analytics Schemas ────────────────────────────────────────────────────────

class ThreatBreakdown(BaseModel):
    critical: int = 0
    high:     int = 0
    medium:   int = 0
    low:      int = 0
    none:     int = 0

class AnalyticsResponse(BaseModel):
    total_detections:  int
    total_alerts:      int
    people_count:      int
    vehicle_count:     int
    loitering_count:   int
    intrusion_count:   int
    cameras_online:    int
    cameras_total:     int
    ai_engine_fps:     float
    processing_time_ms: float
    threat_breakdown:  ThreatBreakdown


# ─── Zone Schemas ─────────────────────────────────────────────────────────────

class ZoneType(str, Enum):
    RESTRICTED = "RESTRICTED"
    EXCLUSION  = "EXCLUSION"
    BUFFER     = "BUFFER"

class SourceType(str, Enum):
    CAMERA = "CAMERA"
    WEBCAM = "WEBCAM"
    VIDEO  = "VIDEO"

class ZoneCreate(BaseModel):
    source_id:   str
    source_type: Optional[SourceType] = SourceType.CAMERA
    name:        Optional[str]        = "Restricted Zone A"
    coordinates: List[List[float]]    # [[x, y], ...] in 0-100%
    enabled:     Optional[bool]       = True
    zone_type:   Optional[ZoneType]   = ZoneType.RESTRICTED

class ZoneUpdate(BaseModel):
    name:        Optional[str]        = None
    coordinates: Optional[List[List[float]]] = None
    enabled:     Optional[bool]       = None
    zone_type:   Optional[ZoneType]   = None

class ZoneResponse(BaseModel):
    id:          str
    source_id:   str
    source_type: str
    name:        str
    coordinates: List[List[float]]
    enabled:     bool
    zone_type:   str
    created_at:  datetime
    updated_at:  datetime

    model_config = {"from_attributes": True}


# ─── Watchlist & Face Recognition Schemas ─────────────────────────────────────

class WatchlistPersonCreate(BaseModel):
    name:            str
    identifier:      Optional[str] = None
    notes:           Optional[str] = None
    threat_priority: Optional[str] = "HIGH"
    is_active:       Optional[bool] = True

class WatchlistPersonUpdate(BaseModel):
    name:            Optional[str] = None
    identifier:      Optional[str] = None
    notes:           Optional[str] = None
    threat_priority: Optional[str] = None
    is_active:       Optional[bool] = None

class FaceEmbeddingResponse(BaseModel):
    id:         str
    person_id:  str
    created_at: datetime

    model_config = {"from_attributes": True}

class WatchlistPersonResponse(BaseModel):
    id:              str
    name:            str
    identifier:      Optional[str] = None
    notes:           Optional[str] = None
    threat_priority: str
    is_active:       bool
    photo_path:      Optional[str] = None
    embeddings_count: int = 0
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}

class FaceMatchResult(BaseModel):
    is_match:     bool
    person_id:    Optional[str]   = None
    person_name:  Optional[str]   = None
    identifier:   Optional[str]   = None
    similarity:   float           = 0.0 # 0.0 - 100.0%
    cosine_score: float           = 0.0
    threat_level: Optional[str]   = None

class TestFaceMatchResponse(BaseModel):
    face_detected: bool
    match_found:   bool
    person_id:     Optional[str]   = None
    person_name:   Optional[str]   = None
    similarity:    float           = 0.0
    cosine_score:  float           = 0.0
    threshold_used: float          = 0.45
    message:       str


# ─── ANPR Schemas ─────────────────────────────────────────────────────────────

class ANPRPlateResult(BaseModel):
    plate_detected:   bool
    plate_text:       Optional[str]   = None
    plate_confidence: Optional[float] = None
    plate_status:     str             = "NOT_DETECTED" # READABLE | UNREADABLE | UNCERTAIN | NOT_DETECTED
    plate_bbox:       Optional[dict]  = None

class ANPREventResponse(BaseModel):
    id:               str
    camera_id:        Optional[str]   = None
    video_id:         Optional[str]   = None
    vehicle_track_id: int
    vehicle_type:     str
    plate_text:       Optional[str]   = None
    plate_confidence: Optional[float] = None
    plate_status:     str
    video_time_sec:   Optional[float] = None
    snapshot_path:    Optional[str]   = None
    timestamp:        datetime
    created_at:       datetime

    model_config = {"from_attributes": True}

class ANPRStatsResponse(BaseModel):
    total_vehicles_tracked: int
    total_plates_detected:  int
    readable_plates_count:  int
    unreadable_plates_count: int
    unique_plates:          List[str]

class TestANPRResponse(BaseModel):
    plate_detected:   bool
    plate_text:       Optional[str]   = None
    plate_confidence: Optional[float] = None
    plate_status:     str
    cleaned_text:     Optional[str]   = None
    message:          str



