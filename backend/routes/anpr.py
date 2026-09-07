"""
IBVAP ANPR Router — Automatic Number Plate Recognition APIs
============================================================
Provides REST endpoints for querying real ANPR events,
evaluating plate test snapshots, and querying vehicle plate statistics.
"""
import os
import cv2
import base64
import numpy as np
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from database.database import get_db
from models.models import ANPREvent
from schemas.schemas import ANPREventResponse, ANPRStatsResponse, TestANPRResponse
from ai_engine.intelligence.anpr_engine import get_anpr_engine

logger = logging.getLogger("anpr_route")

router = APIRouter(prefix="/api/anpr", tags=["ANPR"])


@router.get("/events", response_model=List[ANPREventResponse])
def get_anpr_events(
    camera_id: Optional[str] = None,
    plate_text: Optional[str] = None,
    plate_status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Returns stored ANPR events from SQLite database.
    Filterable by camera_id, plate_text substring, or plate_status.
    """
    query = db.query(ANPREvent)
    if camera_id:
        query = query.filter(ANPREvent.camera_id == camera_id)
    if plate_text:
        query = query.filter(ANPREvent.plate_text.ilike(f"%{plate_text}%"))
    if plate_status:
        query = query.filter(ANPREvent.plate_status == plate_status)

    events = query.order_by(desc(ANPREvent.timestamp)).limit(limit).all()
    return events


@router.get("/stats", response_model=ANPRStatsResponse)
def get_anpr_stats(db: Session = Depends(get_db)):
    """
    Returns aggregated ANPR statistics directly computed from the SQLite database.
    """
    total_events = db.query(ANPREvent).count()
    readable_count = db.query(ANPREvent).filter(ANPREvent.plate_status == "READABLE").count()
    unreadable_count = db.query(ANPREvent).filter(ANPREvent.plate_status.in_(["UNREADABLE", "UNCERTAIN"])).count()

    unique_plates_query = (
        db.query(ANPREvent.plate_text)
        .filter(ANPREvent.plate_text.isnot(None), ANPREvent.plate_status == "READABLE")
        .distinct()
        .all()
    )
    unique_plates = [p[0] for p in unique_plates_query if p[0]]

    return ANPRStatsResponse(
        total_vehicles_tracked=total_events,
        total_plates_detected=readable_count + unreadable_count,
        readable_plates_count=readable_count,
        unreadable_plates_count=unreadable_count,
        unique_plates=unique_plates
    )


@router.post("/test-recognize", response_model=TestANPRResponse)
async def test_recognize_plate(
    image: Optional[UploadFile] = File(None),
    image_base64: Optional[str] = Form(None)
):
    """
    Probes the real ANPR engine with a vehicle photo or plate crop.
    Runs license plate localization and CRNN OCR.
    """
    engine = get_anpr_engine()
    if not engine.is_ready:
        raise HTTPException(status_code=503, detail="ANPR Engine is not initialized")

    img_bgr = None

    if image is not None:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif image_base64:
        header_removed = image_base64
        if "base64," in header_removed:
            header_removed = header_removed.split("base64,")[1]
        raw_bytes = base64.b64decode(header_removed)
        nparr = np.frombuffer(raw_bytes, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_bgr is None or img_bgr.size == 0:
        raise HTTPException(status_code=400, detail="Invalid image provided")

    # If image is a tight plate crop (aspect ratio > 1.8), test OCR directly
    h, w = img_bgr.shape[:2]
    aspect_ratio = float(w) / float(h) if h > 0 else 0

    if aspect_ratio >= 1.8 and h <= 150:
        plate_text, confidence, status = engine.recognize_plate(img_bgr)
        return TestANPRResponse(
            plate_detected=True,
            plate_text=plate_text,
            plate_confidence=confidence if plate_text else None,
            plate_status=status,
            cleaned_text=plate_text,
            message="Direct plate crop recognized via CRNN OCR"
        )

    # Otherwise locate plate region within vehicle image
    plate_found, plate_crop, plate_bbox = engine.locate_plate_region(img_bgr)
    if not plate_found or plate_crop is None:
        return TestANPRResponse(
            plate_detected=False,
            plate_text=None,
            plate_confidence=None,
            plate_status="NOT_DETECTED",
            cleaned_text=None,
            message="No license plate structure detected in the vehicle image"
        )

    plate_text, confidence, status = engine.recognize_plate(plate_crop)
    return TestANPRResponse(
        plate_detected=True,
        plate_text=plate_text,
        plate_confidence=confidence if plate_text else None,
        plate_status=status,
        cleaned_text=plate_text,
        message=f"Plate detected and processed with status: {status}"
    )


# ─── Watchlist Plate Management ───────────────────────────────────────────────

from models.models import WatchlistPlate
from schemas.schemas import WatchlistPlateCreate, WatchlistPlateResponse
import uuid


@router.get("/watchlist", response_model=List[WatchlistPlateResponse])
def get_watchlist_plates(db: Session = Depends(get_db)):
    """Returns all registered suspect/wanted vehicle plates."""
    return db.query(WatchlistPlate).order_by(desc(WatchlistPlate.created_at)).all()


@router.post("/watchlist", response_model=WatchlistPlateResponse)
def add_watchlist_plate(data: WatchlistPlateCreate, db: Session = Depends(get_db)):
    """Registers a suspect license plate for automated threat alerting."""
    normalized = data.plate_number.replace(" ", "").upper()
    existing = db.query(WatchlistPlate).filter(WatchlistPlate.plate_number == normalized).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Plate {normalized} is already in the watchlist.")

    rec = WatchlistPlate(
        id=str(uuid.uuid4()),
        plate_number=normalized,
        vehicle_owner=data.vehicle_owner,
        vehicle_model=data.vehicle_model,
        threat_priority=data.threat_priority or "HIGH",
        reason=data.reason,
        is_active=True,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/watchlist/{plate_id}")
def delete_watchlist_plate(plate_id: str, db: Session = Depends(get_db)):
    """Removes a suspect plate from the watchlist."""
    rec = db.query(WatchlistPlate).filter(WatchlistPlate.id == plate_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Watchlist plate not found")
    db.delete(rec)
    db.commit()
    return {"status": "deleted", "id": plate_id}
