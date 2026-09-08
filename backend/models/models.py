from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database.database import Base
from datetime import datetime
import uuid


def _uid():
    return str(uuid.uuid4())


# ─── Camera ───────────────────────────────────────────────────────────────────

class Camera(Base):
    __tablename__ = "cameras"

    id            = Column(String, primary_key=True, default=_uid)
    name          = Column(String, nullable=False, unique=True, index=True)
    location      = Column(String, nullable=False, default="Surveillance Area")
    source_type   = Column(String, default="CCTV")         # CCTV | PHONE | WEBCAM
    stream_url    = Column(String, nullable=True)          # rtsp://... | http://...
    stream_type   = Column(String, default="RTSP")         # RTSP | MJPEG | HTTP | WEBCAM
    status        = Column(String, default="ONLINE")       # ONLINE | OFFLINE | ERROR
    ai_status     = Column(String, default="STOPPED")      # RUNNING | STOPPED | ERROR
    fps           = Column(Float,  default=25.0)
    resolution    = Column(String, default="1920x1080")
    last_activity = Column(DateTime, default=datetime.utcnow)
    created_at    = Column(DateTime, default=datetime.utcnow)

    videos     = relationship("Video",     back_populates="camera", cascade="all, delete")
    detections = relationship("Detection", back_populates="camera", cascade="all, delete")
    alerts     = relationship("Alert",     back_populates="camera", cascade="all, delete")



# ─── Video ────────────────────────────────────────────────────────────────────

class Video(Base):
    __tablename__ = "videos"

    id          = Column(String, primary_key=True, default=_uid)
    filename    = Column(String, nullable=False)
    camera_id   = Column(String, ForeignKey("cameras.id"), nullable=True)
    status      = Column(String, default="READY")    # READY|UPLOADING|PROCESSING|AI_ANALYZING|COMPLETED|ERROR
    file_path   = Column(String, nullable=True)
    file_size   = Column(Integer, nullable=True)
    duration    = Column(Float,  nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    camera     = relationship("Camera",    back_populates="videos")
    detections = relationship("Detection", back_populates="video", cascade="all, delete")


# ─── Detection ────────────────────────────────────────────────────────────────

class Detection(Base):
    __tablename__ = "detections"

    id                    = Column(String,  primary_key=True, default=_uid)
    camera_id             = Column(String,  ForeignKey("cameras.id"), nullable=False, index=True)
    video_id              = Column(String,  ForeignKey("videos.id"),  nullable=True)
    object_type           = Column(String,  nullable=False)   # PERSON | VEHICLE | ANIMAL | UNKNOWN
    object_id             = Column(String,  nullable=False)
    confidence            = Column(Float,   nullable=False)
    zone                  = Column(String,  nullable=True)
    event_type            = Column(String,  nullable=False)
    bbox_x                = Column(Float,   default=0.0)
    bbox_y                = Column(Float,   default=0.0)
    bbox_w                = Column(Float,   default=0.0)
    bbox_h                = Column(Float,   default=0.0)
    is_in_restricted_zone = Column(Boolean, default=False)
    loitering_duration    = Column(Integer, nullable=True)
    timestamp             = Column(DateTime, default=datetime.utcnow, index=True)
    # ── Video-relative frame identity (populated only for uploaded-video detections) ──
    frame_index           = Column(Integer, nullable=True)   # 0-based frame counter
    video_time_sec        = Column(Float,   nullable=True)   # frame_index / source_fps

    # ── ANPR License Plate Association (Real Plate Detection & OCR) ──
    plate_text            = Column(String,  nullable=True, index=True) # e.g. "DL01AB1234"
    plate_confidence      = Column(Float,   nullable=True)             # 0-100%
    plate_status          = Column(String,  nullable=True)             # READABLE | UNREADABLE | UNCERTAIN | NOT_DETECTED
    plate_bbox_x          = Column(Float,   nullable=True)
    plate_bbox_y          = Column(Float,   nullable=True)
    plate_bbox_w          = Column(Float,   nullable=True)
    plate_bbox_h          = Column(Float,   nullable=True)

    # ── Night Vision Provenance (Real Low-Light Measurement & Enhancement) ──
    night_vision_applied  = Column(Boolean, default=False)
    frame_luminance       = Column(Float,   nullable=True)
    lighting_profile      = Column(String,  nullable=True)  # DAY | DUSK | NIGHT | EXTREME_LOW

    camera = relationship("Camera", back_populates="detections")
    video  = relationship("Video",  back_populates="detections")

    @property
    def bbox(self):
        return {"x": self.bbox_x, "y": self.bbox_y, "w": self.bbox_w, "h": self.bbox_h}

    @property
    def plate_info(self):
        if not self.plate_status or self.plate_status == "NOT_DETECTED":
            return None
        p_bbox = None
        if self.plate_bbox_w and self.plate_bbox_w > 0:
            p_bbox = {
                "x": self.plate_bbox_x or 0.0,
                "y": self.plate_bbox_y or 0.0,
                "w": self.plate_bbox_w or 0.0,
                "h": self.plate_bbox_h or 0.0
            }
        return {
            "plate_detected": True,
            "plate_text": self.plate_text,
            "plate_confidence": self.plate_confidence,
            "plate_status": self.plate_status,
            "plate_bbox": p_bbox,
            "vehicle_type": self.object_type,
        }



# ─── Alert ────────────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"

    id            = Column(String,  primary_key=True, default=_uid)
    alert_id      = Column(String,  nullable=False, unique=True, index=True)
    camera_id     = Column(String,  ForeignKey("cameras.id"), nullable=False, index=True)
    video_id      = Column(String,  ForeignKey("videos.id"),  nullable=True, index=True)
    event_type    = Column(String,  nullable=False)
    object_type   = Column(String,  nullable=False)
    object_id     = Column(String,  nullable=False)
    threat_level  = Column(String,  nullable=False)   # CRITICAL | HIGH | MEDIUM | LOW | NONE
    reason        = Column(Text,    nullable=False)
    confidence    = Column(Float,   nullable=True)
    bbox_x        = Column(Float,   default=0.0)
    bbox_y        = Column(Float,   default=0.0)
    bbox_w        = Column(Float,   default=0.0)
    bbox_h        = Column(Float,   default=0.0)
    status        = Column(String,  default="NEW", index=True)  # NEW | ACKNOWLEDGED | UNDER_INVESTIGATION | RESOLVED
    snapshot_path = Column(String,  nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    camera = relationship("Camera", back_populates="alerts")
    video  = relationship("Video")


# ─── Zone ─────────────────────────────────────────────────────────────────────

class Zone(Base):
    __tablename__ = "zones"

    id               = Column(String,  primary_key=True, default=_uid)
    source_id        = Column(String,  nullable=False, unique=True, index=True) # e.g. "BOP-01", "WEBCAM-01", video_id
    source_type      = Column(String,  default="CAMERA")                        # CAMERA | WEBCAM | VIDEO
    name             = Column(String,  default="Restricted Zone A")
    coordinates_json = Column(Text,    nullable=False)                          # JSON array of [x, y] in %
    enabled          = Column(Boolean, default=True)
    zone_type        = Column(String,  default="RESTRICTED")                    # RESTRICTED | EXCLUSION | BUFFER
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Watchlist Person ─────────────────────────────────────────────────────────

class WatchlistPerson(Base):
    __tablename__ = "watchlist_persons"

    id              = Column(String,  primary_key=True, default=_uid)
    name            = Column(String,  nullable=False, index=True)
    identifier      = Column(String,  nullable=True, index=True) # e.g. "POI-9821" / "Badge #401"
    notes           = Column(Text,    nullable=True)
    threat_priority = Column(String,  default="HIGH")           # CRITICAL | HIGH | MEDIUM | LOW
    is_active       = Column(Boolean, default=True, index=True)
    photo_path      = Column(String,  nullable=True)            # Relative path to saved face photo
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    embeddings = relationship("FaceEmbedding", back_populates="person", cascade="all, delete-orphan")
    events     = relationship("FaceRecognitionEvent", back_populates="person", cascade="all, delete-orphan")


# ─── Face Embedding ───────────────────────────────────────────────────────────

class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id             = Column(String,  primary_key=True, default=_uid)
    person_id      = Column(String,  ForeignKey("watchlist_persons.id"), nullable=False, index=True)
    embedding_json = Column(Text,    nullable=False) # JSON array of 128 float values (SFace)
    created_at     = Column(DateTime, default=datetime.utcnow)

    person = relationship("WatchlistPerson", back_populates="embeddings")


# ─── Face Recognition Event ───────────────────────────────────────────────────

class FaceRecognitionEvent(Base):
    __tablename__ = "face_recognition_events"

    id           = Column(String,  primary_key=True, default=_uid)
    person_id    = Column(String,  ForeignKey("watchlist_persons.id"), nullable=True, index=True)
    person_name  = Column(String,  nullable=True)
    camera_id    = Column(String,  nullable=False, index=True)
    video_id     = Column(String,  nullable=True, index=True)
    track_id     = Column(Integer, nullable=True)
    similarity   = Column(Float,   nullable=False) # 0.0 - 100.0 %
    cosine_score = Column(Float,   nullable=False) # raw cosine similarity
    event_type   = Column(String,  default="WATCHLIST_MATCH") # WATCHLIST_MATCH | UNKNOWN_FACE
    timestamp    = Column(DateTime, default=datetime.utcnow, index=True)

    person = relationship("WatchlistPerson", back_populates="events")


# ─── ANPR Event ───────────────────────────────────────────────────────────────

class ANPREvent(Base):
    __tablename__ = "anpr_events"

    id               = Column(String,  primary_key=True, default=_uid)
    camera_id        = Column(String,  nullable=True, index=True)
    video_id         = Column(String,  nullable=True, index=True)
    vehicle_track_id = Column(Integer, nullable=False, index=True)
    vehicle_type     = Column(String,  nullable=False, default="CAR") # CAR | TRUCK | BUS | MOTORCYCLE
    plate_text       = Column(String,  nullable=True, index=True)     # e.g. "DL01AB1234"
    plate_confidence = Column(Float,   nullable=True)                 # 0.0 - 100.0%
    plate_status     = Column(String,  nullable=False, default="READABLE") # READABLE | UNREADABLE | UNCERTAIN | NOT_DETECTED
    bbox_x           = Column(Float,   default=0.0)
    bbox_y           = Column(Float,   default=0.0)
    bbox_w           = Column(Float,   default=0.0)
    bbox_h           = Column(Float,   default=0.0)
    snapshot_path    = Column(String,  nullable=True)
    video_time_sec   = Column(Float,   nullable=True)
    timestamp        = Column(DateTime, default=datetime.utcnow, index=True)
    created_at       = Column(DateTime, default=datetime.utcnow)


# ─── Vehicle Plate Watchlist ──────────────────────────────────────────────────

class WatchlistPlate(Base):
    __tablename__ = "watchlist_plates"

    id              = Column(String,  primary_key=True, default=_uid)
    plate_number    = Column(String,  nullable=False, unique=True, index=True) # Normalized plate (e.g. "DL01AB1234")
    vehicle_owner   = Column(String,  nullable=True)                           # Owner / Suspect Name
    vehicle_model   = Column(String,  nullable=True)                           # e.g. "White Sedan"
    threat_priority = Column(String,  default="HIGH")                          # CRITICAL | HIGH | MEDIUM | LOW
    reason          = Column(Text,    nullable=True)                           # Stolen / Wanted / Restricted
    is_active       = Column(Boolean, default=True, index=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
