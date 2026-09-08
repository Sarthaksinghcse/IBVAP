from pydantic import BaseModel, Field
from typing import Optional, List, Literal
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
    CCTV   = "CCTV"
    PHONE  = "PHONE"
    WEBCAM = "WEBCAM"

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

# Phase 1.4 (D3): Validated threat priority enum
class ThreatPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"


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

class CameraUpdate(BaseModel):
    name:        Optional[str] = None
    location:    Optional[str] = None
    status:      Optional[CameraStatus] = None
    ai_status:   Optional[AIStatus] = None
    stream_url:  Optional[str] = None
    stream_type: Optional[str] = None
    fps:         Optional[float] = None
    resolution:  Optional[str] = None

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
    last_activity: datetime
    created_at:    Optional[datetime] = None

    model_config = {"from_attributes": True}



# ─── Video Schemas ────────────────────────────────────────────────────────────

class VideoResponse(BaseModel):
    id:         str
    filename:   str
    camera_id:  Optional[str]   = None
    status:     VideoStatus
    file_path:  Optional[str]   = None
    file_size:  Optional[int]   = None
    duration:   Optional[float] = None
    created_at: datetime

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
    # Video-relative frame identity — populated only for uploaded-video detections
    frame_index:           Optional[int]   = None
    video_time_sec:        Optional[float] = None
    plate_info:            Optional[PlateInfoSchema] = None

class DetectionResponse(BaseModel):
    id:                    str
    camera_id:             str
    video_id:              Optional[str]   = None
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
    confidence_kind: Optional[str] = None   # Phase 4.5 (D2): DETECTION | FACE_MATCH
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
    confidence_kind: Optional[str] = None   # Phase 4.5 (D2)
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
    # Phase 1.4 (D3): Validated threat priority
    threat_priority: Optional[ThreatPriority] = ThreatPriority.HIGH
    is_active:       Optional[bool] = True

class WatchlistPersonUpdate(BaseModel):
    name:            Optional[str] = None
    identifier:      Optional[str] = None
    notes:           Optional[str] = None
    # Phase 1.4 (D3): Validated threat priority
    threat_priority: Optional[ThreatPriority] = None
    is_active:       Optional[bool] = None

class FaceEmbeddingResponse(BaseModel):
    id:         str
    person_id:  str
    photo_path: Optional[str] = None
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
    original_filename: Optional[str] = None
    embeddings_count: int = 0
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}

# Phase 3.1: Photo gallery response
class PhotoGalleryItem(BaseModel):
    embedding_id:  str
    photo_path:    Optional[str] = None
    quality_score: Optional[float] = None
    created_at:    datetime

class PersonPhotoGalleryResponse(BaseModel):
    person_id:     str
    person_name:   str
    primary_photo: Optional[str] = None
    photos:        List[PhotoGalleryItem] = []

class FaceMatchCandidate(BaseModel):
    person_id:     str
    name:          Optional[str] = None
    identifier:    Optional[str] = None
    threat_priority: Optional[str] = None
    cosine_score:  float = 0.0
    similarity:    float = 0.0
    calibrated_confidence: float = 0.0

class FaceMatchResult(BaseModel):
    is_match:     bool
    person_id:    Optional[str]   = None
    person_name:  Optional[str]   = None
    identifier:   Optional[str]   = None
    similarity:   float           = 0.0 # 0.0 - 100.0%
    cosine_score: float           = 0.0
    calibrated_confidence: float  = 0.0
    threat_level: Optional[str]   = None
    top_candidates: List[FaceMatchCandidate] = []

class TestFaceMatchResponse(BaseModel):
    face_detected: bool
    match_found:   bool
    person_id:     Optional[str]   = None
    person_name:   Optional[str]   = None
    similarity:    float           = 0.0
    cosine_score:  float           = 0.0
    calibrated_confidence: float   = 0.0
    threshold_used: float          = 0.45
    message:       str
    top_candidates: List[FaceMatchCandidate] = []

# Phase 1.3: Face recognition event schemas
class FaceRecognitionEventResponse(BaseModel):
    id:           str
    person_id:    Optional[str]   = None
    person_name:  Optional[str]   = None
    camera_id:    str
    video_id:     Optional[str]   = None
    track_id:     Optional[int]   = None
    similarity:   float
    cosine_score: float
    event_type:   str
    snapshot_path: Optional[str]  = None
    timestamp:    datetime

    model_config = {"from_attributes": True}

# Phase 2.1: Watchlist embeddings for pipeline sync
class WatchlistEmbeddingRecord(BaseModel):
    person_id:      str
    name:           str
    identifier:     Optional[str] = None
    threat_priority: str
    embedding:      List[float]

class WatchlistEmbeddingsResponse(BaseModel):
    version:  int
    records:  List[WatchlistEmbeddingRecord]

# Phase 5.3: Audit log schemas
class WatchlistAuditLogResponse(BaseModel):
    id:            str
    actor:         str
    action:        str
    person_id:     Optional[str] = None
    person_name:   Optional[str] = None
    justification: Optional[str] = None
    details:       Optional[str] = None
    timestamp:     datetime

    model_config = {"from_attributes": True}


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
