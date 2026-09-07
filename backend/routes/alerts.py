from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from database.database import get_db
from models.models import Alert
from schemas.schemas import AlertCreate, AlertUpdate, AlertResponse
from websocket.manager import manager
from datetime import datetime
import uuid

router = APIRouter()


def _gen_alert_id() -> str:
    date_str = datetime.utcnow().strftime("%Y%m%d")
    short    = str(uuid.uuid4())[:8].upper()
    return f"ALERT-{date_str}-{short}"


@router.get("/", response_model=List[AlertResponse])
def get_alerts(
    status:       Optional[str] = None,
    threat_level: Optional[str] = None,
    camera_id:    Optional[str] = None,
    video_id:     Optional[str] = None,
    limit:        int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Alert)
    if status:       q = q.filter(Alert.status       == status)
    if threat_level: q = q.filter(Alert.threat_level == threat_level)
    if camera_id:    q = q.filter(Alert.camera_id    == camera_id)
    if video_id:     q = q.filter(Alert.video_id     == video_id)
    items = q.order_by(Alert.created_at.desc()).limit(limit).all()
    return [_to_alert_response(a) for a in items]


@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _to_alert_response(alert)


@router.post("/", response_model=AlertResponse)
async def create_alert(data: AlertCreate, db: Session = Depends(get_db)):
    """
    Called by: ThreatEngine / AI Pipeline (POST /api/alerts)
    Side effect: Persists to DB and Broadcasts to ALL WebSocket clients
    """
    now = datetime.utcnow()
    bbox_dict = data.bbox.model_dump() if data.bbox else {}

    alert = Alert(
        id            = str(uuid.uuid4()),
        alert_id      = _gen_alert_id(),
        camera_id     = data.camera_id,
        video_id      = data.video_id,
        event_type    = data.event_type,
        object_type   = data.object_type,
        object_id     = data.object_id,
        threat_level  = data.threat_level,
        reason        = data.reason,
        confidence    = data.confidence,
        bbox_x        = bbox_dict.get("x", 0.0),
        bbox_y        = bbox_dict.get("y", 0.0),
        bbox_w        = bbox_dict.get("w", 0.0),
        bbox_h        = bbox_dict.get("h", 0.0),
        status        = "NEW",
        snapshot_path = data.snapshot_path,
        created_at    = now,
        updated_at    = now,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    resp = _to_alert_response(alert)

    # ── WebSocket broadcast ───────────────────────────────────────────────────
    await manager.broadcast({
        "type": "ALERT",
        "data": resp,
        "timestamp": now.isoformat(),
    })

    return resp


def create_and_broadcast_alert_sync(data_dict: dict) -> dict:
    """
    Direct in-process alert creation and persistence with WebSocket broadcast.
    Used by ThreatEngine / AI Pipeline threads.
    """
    from database.database import SessionLocal
    db = SessionLocal()
    now = datetime.utcnow()
    try:
        bbox_dict = data_dict.get("bbox") or {}
        alert = Alert(
            id            = str(uuid.uuid4()),
            alert_id      = _gen_alert_id(),
            camera_id     = data_dict.get("camera_id") or "WEBCAM-01",
            video_id      = data_dict.get("video_id"),
            event_type    = data_dict.get("event_type") or "ZONE_INTRUSION",
            object_type   = data_dict.get("object_type") or "PERSON",
            object_id     = data_dict.get("object_id") or "Person #1",
            threat_level  = data_dict.get("threat_level") or "HIGH",
            reason        = data_dict.get("reason") or "Security zone event detected.",
            confidence    = data_dict.get("confidence"),
            bbox_x        = bbox_dict.get("x", 0.0),
            bbox_y        = bbox_dict.get("y", 0.0),
            bbox_w        = bbox_dict.get("w", 0.0),
            bbox_h        = bbox_dict.get("h", 0.0),
            status        = "NEW",
            snapshot_path = data_dict.get("snapshot_path"),
            created_at    = now,
            updated_at    = now,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        resp = _to_alert_response(alert)
        manager.broadcast_sync({
            "type": "ALERT",
            "data": resp,
            "timestamp": now.isoformat(),
        })
        return resp
    finally:
        db.close()



def _to_alert_response(alert: Alert) -> dict:
    """Format ORM Alert model into API response dict with optional bbox."""
    bbox = None
    if alert.bbox_w and alert.bbox_w > 0:
        bbox = {
            "x": alert.bbox_x,
            "y": alert.bbox_y,
            "w": alert.bbox_w,
            "h": alert.bbox_h,
        }
    return {
        "id":            alert.id,
        "alert_id":      alert.alert_id,
        "camera_id":     alert.camera_id,
        "video_id":      alert.video_id,
        "event_type":    alert.event_type,
        "object_type":   alert.object_type,
        "object_id":     alert.object_id,
        "threat_level":  alert.threat_level,
        "reason":        alert.reason,
        "confidence":    alert.confidence,
        "bbox":          bbox,
        "status":        alert.status,
        "snapshot_path": alert.snapshot_path,
        "created_at":    alert.created_at,
        "updated_at":    alert.updated_at,
    }


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(alert_id: str, data: AlertUpdate, db: Session = Depends(get_db)):
    """
    Called by: Web Portal or Security Software to acknowledge / update status.
    Both see the same database — status updates are shared automatically.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status     = data.status
    alert.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)

    # Broadcast status change to all clients
    await manager.broadcast({
        "type": "ALERT_UPDATE",
        "data": {"id": alert.id, "status": alert.status},
        "timestamp": alert.updated_at.isoformat(),
    })

    return alert
