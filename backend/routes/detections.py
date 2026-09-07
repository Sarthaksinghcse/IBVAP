from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from database.database import get_db
from models.models import Detection
from schemas.schemas import DetectionCreate, DetectionResponse, BBoxSchema
from websocket.manager import manager
from datetime import datetime
import uuid

router = APIRouter()


@router.get("/", response_model=List[DetectionResponse])
def get_detections(
    camera_id: Optional[str] = None,
    video_id:  Optional[str] = None,
    limit:     int = 5000,
    db: Session = Depends(get_db),
):
    q = db.query(Detection)
    if camera_id:
        q = q.filter(Detection.camera_id == camera_id)
    if video_id:
        q = q.filter(Detection.video_id == video_id)
    
    # Chronological if specific to a video, newest first for live camera
    if video_id:
        items = q.order_by(Detection.timestamp.asc()).limit(limit).all()
    else:
        items = q.order_by(Detection.timestamp.desc()).limit(limit).all()

    return [_to_response(d) for d in items]


@router.post("/", response_model=DetectionResponse)
async def create_detection(data: DetectionCreate, db: Session = Depends(get_db)):
    """Called by the AI Engine to log each detection frame event."""
    ts = data.timestamp or datetime.utcnow()
    det = Detection(
        id                    = str(uuid.uuid4()),
        camera_id             = data.camera_id,
        video_id              = data.video_id,
        object_type           = data.object_type,
        object_id             = data.object_id,
        confidence            = data.confidence,
        zone                  = data.zone,
        event_type            = data.event_type,
        bbox_x                = data.bbox.x,
        bbox_y                = data.bbox.y,
        bbox_w                = data.bbox.w,
        bbox_h                = data.bbox.h,
        is_in_restricted_zone = data.is_in_restricted_zone or False,
        loitering_duration    = data.loitering_duration,
        timestamp             = ts,
        frame_index           = data.frame_index,
        video_time_sec        = data.video_time_sec,
        plate_text            = data.plate_info.plate_text if data.plate_info else None,
        plate_confidence      = data.plate_info.plate_confidence if data.plate_info else None,
        plate_status          = data.plate_info.plate_status if data.plate_info else None,
        plate_bbox_x          = data.plate_info.plate_bbox.x if data.plate_info and data.plate_info.plate_bbox else None,
        plate_bbox_y          = data.plate_info.plate_bbox.y if data.plate_info and data.plate_info.plate_bbox else None,
        plate_bbox_w          = data.plate_info.plate_bbox.w if data.plate_info and data.plate_info.plate_bbox else None,
        plate_bbox_h          = data.plate_info.plate_bbox.h if data.plate_info and data.plate_info.plate_bbox else None,
    )
    db.add(det)
    db.commit()
    db.refresh(det)

    resp = _to_response(det)
    await manager.broadcast({
        "type": "DETECTION",
        "data": resp,
        "timestamp": ts.isoformat(),
    })

    return resp


def _to_response(det: Detection) -> dict:
    """Convert ORM object to response dict (bbox and plate_info need reconstruction)."""
    p_info = None
    if det.plate_status and det.plate_status != "NOT_DETECTED":
        p_bbox = None
        if det.plate_bbox_w and det.plate_bbox_w > 0:
            p_bbox = {
                "x": det.plate_bbox_x or 0.0,
                "y": det.plate_bbox_y or 0.0,
                "w": det.plate_bbox_w or 0.0,
                "h": det.plate_bbox_h or 0.0,
            }
        p_info = {
            "plate_detected": True,
            "plate_text": det.plate_text,
            "plate_confidence": det.plate_confidence,
            "plate_status": det.plate_status,
            "plate_bbox": p_bbox,
            "vehicle_type": det.object_type,
        }

    return {
        "id":                    det.id,
        "camera_id":             det.camera_id,
        "video_id":              det.video_id,
        "object_type":           det.object_type,
        "object_id":             det.object_id,
        "confidence":            det.confidence,
        "zone":                  det.zone,
        "event_type":            det.event_type,
        "bbox":                  {"x": det.bbox_x, "y": det.bbox_y, "w": det.bbox_w, "h": det.bbox_h},
        "is_in_restricted_zone": det.is_in_restricted_zone,
        "loitering_duration":    det.loitering_duration,
        "timestamp":             det.timestamp,
        "frame_index":           det.frame_index,
        "video_time_sec":        det.video_time_sec,
        "plate_info":            p_info,
    }
