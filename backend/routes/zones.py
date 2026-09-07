from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import json, uuid, logging
from datetime import datetime

from database.database import get_db
from models.models import Zone
from schemas.schemas import ZoneCreate, ZoneUpdate, ZoneResponse

logger = logging.getLogger("zones_route")
router = APIRouter()


def _zone_to_response(z: Zone) -> dict:
    coords = []
    if z.coordinates_json:
        try:
            coords = json.loads(z.coordinates_json)
        except Exception as e:
            logger.warning(f"[Zones] Error parsing coordinates_json for {z.source_id}: {e}")
            coords = []
    return {
        "id": z.id,
        "source_id": z.source_id,
        "source_type": z.source_type,
        "name": z.name,
        "coordinates": coords,
        "enabled": z.enabled,
        "zone_type": z.zone_type,
        "created_at": z.created_at,
        "updated_at": z.updated_at,
    }


@router.get("/", response_model=List[ZoneResponse])
def get_all_zones(db: Session = Depends(get_db)):
    """Retrieve all configured zones across all sources."""
    zones = db.query(Zone).order_by(Zone.source_id).all()
    return [_zone_to_response(z) for z in zones]


@router.get("/{source_id}", response_model=ZoneResponse)
def get_zone_by_source(source_id: str, db: Session = Depends(get_db)):
    """Retrieve the configured restricted zone for a specific camera/source/video."""
    zone = db.query(Zone).filter(Zone.source_id == source_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail=f"No zone configured for source '{source_id}'")
    return _zone_to_response(zone)


@router.post("/", response_model=ZoneResponse)
def create_or_upsert_zone(data: ZoneCreate, db: Session = Depends(get_db)):
    """
    Create or update a zone configuration for a specific camera, webcam, or video.
    If a zone already exists for this source_id, it is updated in-place.
    """
    coords_json = json.dumps(data.coordinates)
    existing = db.query(Zone).filter(Zone.source_id == data.source_id).first()

    now = datetime.utcnow()
    if existing:
        existing.name = data.name or existing.name
        existing.source_type = data.source_type.value if hasattr(data.source_type, "value") else str(data.source_type)
        existing.coordinates_json = coords_json
        existing.enabled = data.enabled if data.enabled is not None else existing.enabled
        existing.zone_type = data.zone_type.value if hasattr(data.zone_type, "value") else str(data.zone_type)
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        logger.info(f"[Zones] Updated zone for source '{data.source_id}' with {len(data.coordinates)} points")
        return _zone_to_response(existing)
    else:
        new_zone = Zone(
            id=str(uuid.uuid4()),
            source_id=data.source_id,
            source_type=data.source_type.value if hasattr(data.source_type, "value") else str(data.source_type),
            name=data.name or "Restricted Zone A",
            coordinates_json=coords_json,
            enabled=data.enabled if data.enabled is not None else True,
            zone_type=data.zone_type.value if hasattr(data.zone_type, "value") else str(data.zone_type),
            created_at=now,
            updated_at=now,
        )
        db.add(new_zone)
        db.commit()
        db.refresh(new_zone)
        logger.info(f"[Zones] Created new zone for source '{data.source_id}' with {len(data.coordinates)} points")
        return _zone_to_response(new_zone)


@router.put("/{source_id}", response_model=ZoneResponse)
def update_zone(source_id: str, data: ZoneUpdate, db: Session = Depends(get_db)):
    """Update an existing source zone configuration."""
    zone = db.query(Zone).filter(Zone.source_id == source_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail=f"No zone configured for source '{source_id}'")

    if data.name is not None:
        zone.name = data.name
    if data.coordinates is not None:
        zone.coordinates_json = json.dumps(data.coordinates)
    if data.enabled is not None:
        zone.enabled = data.enabled
    if data.zone_type is not None:
        zone.zone_type = data.zone_type.value if hasattr(data.zone_type, "value") else str(data.zone_type)

    zone.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(zone)
    logger.info(f"[Zones] Updated zone for source '{source_id}'")
    return _zone_to_response(zone)


@router.delete("/{source_id}")
def delete_zone(source_id: str, db: Session = Depends(get_db)):
    """Delete the configured zone for a source."""
    zone = db.query(Zone).filter(Zone.source_id == source_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail=f"No zone configured for source '{source_id}'")

    db.delete(zone)
    db.commit()
    logger.info(f"[Zones] Deleted zone for source '{source_id}'")
    return {"status": "ok", "message": f"Zone for source '{source_id}' removed"}
