"""
IBVAP Backend — Watchlist Management Routes
============================================
Handles registration of persons of interest with real face detection,
SFace 128-D embedding extraction, persistence in SQLite, and test matching.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import uuid
import cv2
import numpy as np
import json
import logging
from datetime import datetime

from database.database import get_db, SessionLocal
from models.models import WatchlistPerson, FaceEmbedding, FaceRecognitionEvent
from schemas.schemas import (
    WatchlistPersonResponse,
    WatchlistPersonUpdate,
    TestFaceMatchResponse,
)
from ai_engine.intelligence.face_engine import get_face_engine

logger = logging.getLogger("watchlist_route")
router = APIRouter()

# Storage directory for watchlist target photos
STORAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "storage", "watchlist"
)
os.makedirs(STORAGE_DIR, exist_ok=True)

# Storage directory for face crops (outside public static mount)
FACE_CROPS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "storage", "face_crops"
)
os.makedirs(FACE_CROPS_DIR, exist_ok=True)


@router.get("/face-crops/{filename}")
def get_face_crop(filename: str):
    """Serves harvested face crops through the watchlist API rather than public static mount."""
    file_path = os.path.join(FACE_CROPS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Face crop not found")
    return FileResponse(file_path)


# Global version counter for watchlist caching
_watchlist_version = 1

def _increment_version():
    global _watchlist_version
    _watchlist_version += 1

def _load_active_watchlist_records(db: Session) -> List[dict]:
    """Helper to fetch all active watchlist persons and their parsed 128-D embeddings."""
    persons = db.query(WatchlistPerson).filter(WatchlistPerson.is_active == True).all()
    records = []
    for p in persons:
        for emb in p.embeddings:
            try:
                vec = np.array(json.loads(emb.embedding_json), dtype=np.float32)
                records.append({
                    "person_id": p.id,
                    "name": p.name,
                    "identifier": p.identifier,
                    "threat_priority": p.threat_priority,
                    "embedding": vec
                })
            except Exception as e:
                logger.warning(f"[Watchlist] Error parsing embedding for person {p.id}: {e}")
    return records


@router.get("/version")
def get_watchlist_version():
    return {"version": _watchlist_version}

@router.get("/embeddings")
def get_watchlist_embeddings(db: Session = Depends(get_db)):
    records = _load_active_watchlist_records(db)
    # Numpy arrays need to be converted to list for JSON serialization
    serialized_records = []
    for r in records:
        r_copy = dict(r)
        r_copy["embedding"] = r["embedding"].tolist()
        serialized_records.append(r_copy)
    return {"version": _watchlist_version, "records": serialized_records}

@router.get("/events")
def get_watchlist_events(limit: int = 100, db: Session = Depends(get_db)):
    events = db.query(FaceRecognitionEvent).order_by(FaceRecognitionEvent.timestamp.desc()).limit(limit).all()
    return events

@router.get("/unknown-faces")
def get_unknown_faces(days: int = 7, min_sightings: int = 2, db: Session = Depends(get_db)):
    # Mock implementation of unknown face clustering for FaceReview.tsx
    # A real implementation would cluster all event embeddings where event_type == 'UNKNOWN_FACE'
    return {"clusters": [], "total_unknown": 0}

@router.get("/", response_model=List[WatchlistPersonResponse])
def list_watchlist_persons(db: Session = Depends(get_db)):
    """Returns all registered watchlist targets ordered by creation time."""
    persons = db.query(WatchlistPerson).order_by(WatchlistPerson.created_at.desc()).all()
    result = []
    for p in persons:
        result.append(WatchlistPersonResponse(
            id=p.id,
            name=p.name,
            identifier=p.identifier,
            notes=p.notes,
            threat_priority=p.threat_priority or "HIGH",
            is_active=p.is_active,
            photo_path=p.photo_path,
            embeddings_count=len(p.embeddings),
            created_at=p.created_at,
            updated_at=p.updated_at or p.created_at,
        ))
    return result


@router.post("/", response_model=WatchlistPersonResponse)
async def register_watchlist_person(
    name: str = Form(...),
    identifier: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    threat_priority: Optional[str] = Form("HIGH"),
    is_active: Optional[bool] = Form(True),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Registers a new person on the Watchlist:
    1. Decodes uploaded image.
    2. Runs real OpenCV YuNet face detection (rejects if no face is found).
    3. Extracts real SFace 128-D embedding vector.
    4. Saves face image locally and stores embedding in SQLite.
    """
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Person name cannot be empty.")

    # Read uploaded image bytes
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded photo is empty.")

    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_bgr is None or img_bgr.size == 0:
        raise HTTPException(status_code=400, detail="Invalid image file format. Please upload a valid JPEG/PNG image.")

    # Run real Face Detection & Embedding Extraction
    face_engine = get_face_engine()
    success, embedding, error_msg = face_engine.process_registration_image(img_bgr)

    if not success or embedding is None:
        raise HTTPException(
            status_code=400,
            detail=error_msg or "No usable face detected. Please upload a clear photo with a visible face."
        )

    # Save photo to storage/watchlist/
    person_id = str(uuid.uuid4())
    safe_filename = f"{person_id[:8]}_{file.filename}"
    file_path = os.path.join(STORAGE_DIR, safe_filename)
    with open(file_path, "wb") as f:
        f.write(contents)

    relative_photo_path = f"/storage/watchlist/{safe_filename}"

    now = datetime.utcnow()
    person = WatchlistPerson(
        id=person_id,
        name=name_clean,
        identifier=identifier.strip() if identifier else None,
        notes=notes.strip() if notes else None,
        threat_priority=threat_priority.upper() if threat_priority else "HIGH",
        is_active=is_active if is_active is not None else True,
        photo_path=relative_photo_path,
        created_at=now,
        updated_at=now,
    )
    db.add(person)
    db.flush()

    # Save 128-D float embedding
    emb_rec = FaceEmbedding(
        id=str(uuid.uuid4()),
        person_id=person.id,
        embedding_json=json.dumps(embedding.tolist()),
        created_at=now,
    )
    db.add(emb_rec)
    db.commit()
    db.refresh(person)

    logger.info(f"[Watchlist] Successfully registered target: {person.name} ({person.id}) with 128-D embedding.")

    # Clear face cache to ensure instant recognition on next frame
    face_engine.clear_cache()
    _increment_version()

    return WatchlistPersonResponse(
        id=person.id,
        name=person.name,
        identifier=person.identifier,
        notes=person.notes,
        threat_priority=person.threat_priority,
        is_active=person.is_active,
        photo_path=person.photo_path,
        embeddings_count=1,
        created_at=person.created_at,
        updated_at=person.updated_at,
    )


@router.get("/{person_id}", response_model=WatchlistPersonResponse)
def get_watchlist_person(person_id: str, db: Session = Depends(get_db)):
    person = db.query(WatchlistPerson).filter(WatchlistPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Watchlist person not found")

    return WatchlistPersonResponse(
        id=person.id,
        name=person.name,
        identifier=person.identifier,
        notes=person.notes,
        threat_priority=person.threat_priority or "HIGH",
        is_active=person.is_active,
        photo_path=person.photo_path,
        embeddings_count=len(person.embeddings),
        created_at=person.created_at,
        updated_at=person.updated_at or person.created_at,
    )


@router.get("/{person_id}/photo")
def get_watchlist_person_photo(person_id: str, db: Session = Depends(get_db)):
    """Serves the enrolled photo for a watchlist target."""
    person = db.query(WatchlistPerson).filter(WatchlistPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Watchlist person not found")
    if not person.photo_path:
        raise HTTPException(status_code=404, detail="Person has no photo registered")

    filename = os.path.basename(person.photo_path)
    file_path = os.path.join(STORAGE_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Photo file not found on disk")

    return FileResponse(file_path)


@router.patch("/{person_id}", response_model=WatchlistPersonResponse)
def update_watchlist_person(person_id: str, data: WatchlistPersonUpdate, db: Session = Depends(get_db)):
    person = db.query(WatchlistPerson).filter(WatchlistPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Watchlist person not found")

    if data.name is not None:
        person.name = data.name.strip()
    if data.identifier is not None:
        person.identifier = data.identifier.strip()
    if data.notes is not None:
        person.notes = data.notes.strip()
    if data.threat_priority is not None:
        person.threat_priority = data.threat_priority.upper()
    if data.is_active is not None:
        person.is_active = data.is_active

    person.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(person)

    get_face_engine().clear_cache()
    _increment_version()
    return WatchlistPersonResponse(
        id=person.id,
        name=person.name,
        identifier=person.identifier,
        notes=person.notes,
        threat_priority=person.threat_priority or "HIGH",
        is_active=person.is_active,
        photo_path=person.photo_path,
        embeddings_count=len(person.embeddings),
        created_at=person.created_at,
        updated_at=person.updated_at,
    )


@router.delete("/{person_id}")
def delete_watchlist_person(person_id: str, db: Session = Depends(get_db)):
    """Deletes a watchlist person, associated embeddings, and saved photo."""
    person = db.query(WatchlistPerson).filter(WatchlistPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Watchlist person not found")

    # Remove photo file if exists
    if person.photo_path and person.photo_path.startswith("/storage/watchlist/"):
        filename = person.photo_path.replace("/storage/watchlist/", "")
        local_path = os.path.join(STORAGE_DIR, filename)
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception as e:
                logger.warning(f"[Watchlist] Could not delete photo file {local_path}: {e}")

    db.delete(person)
    db.commit()

    get_face_engine().clear_cache()
    _increment_version()
    logger.info(f"[Watchlist] Deleted person {person_id}")
    return {"status": "ok", "message": f"Person {person_id} deleted from watchlist"}


@router.post("/test-match", response_model=TestFaceMatchResponse)
async def test_face_match(
    file: UploadFile = File(...),
    threshold: Optional[float] = Form(0.45),
    db: Session = Depends(get_db)
):
    """
    Submits a probe photo to test real face detection and watchlist matching.
    Returns real similarity percentage, cosine score, and matched identity.
    """
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file submitted.")

    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None or img_bgr.size == 0:
        raise HTTPException(status_code=400, detail="Invalid image file format.")

    face_engine = get_face_engine()
    face = face_engine.detect_primary_face(img_bgr, score_threshold=0.50)
    if face is None:
        return TestFaceMatchResponse(
            face_detected=False,
            match_found=False,
            similarity=0.0,
            cosine_score=0.0,
            threshold_used=threshold or 0.45,
            message="No face detected in probe image."
        )

    embedding = face_engine.extract_embedding(img_bgr, face)
    if embedding is None:
        return TestFaceMatchResponse(
            face_detected=True,
            match_found=False,
            similarity=0.0,
            cosine_score=0.0,
            threshold_used=threshold or 0.45,
            message="Face detected but failed to extract embedding vector."
        )

    watchlist_records = _load_active_watchlist_records(db)
    if not watchlist_records:
        return TestFaceMatchResponse(
            face_detected=True,
            match_found=False,
            similarity=0.0,
            cosine_score=0.0,
            threshold_used=threshold or 0.45,
            message="Face detected. No active targets registered in Watchlist database."
        )

    is_match, pid, pname, ident, priority, sim_pct, cos_score = face_engine.match_against_watchlist(
        embedding, watchlist_records, threshold=threshold or 0.45
    )

    if is_match:
        msg = f"MATCH CONFIRMED: {pname} ({ident or 'ID: ' + pid[:8]}) with {sim_pct}% similarity (cosine: {cos_score})."
    else:
        msg = f"UNKNOWN FACE: Best similarity was {sim_pct}% (cosine: {cos_score}, threshold: {threshold or 0.45})."

    return TestFaceMatchResponse(
        face_detected=True,
        match_found=is_match,
        person_id=pid,
        person_name=pname,
        similarity=sim_pct,
        cosine_score=cos_score,
        threshold_used=threshold or 0.45,
        message=msg
    )
