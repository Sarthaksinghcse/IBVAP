"""
IBVAP Backend — Face Authentication Routes
===========================================
Handles biometric face registration, duplicate identity prevention,
and passwordless face-scan authentication using YuNet + SFace.
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import os
import uuid
import json
import base64
import cv2
import numpy as np
import logging

from database.database import get_db
from models.models import User, UserFaceEmbedding
from utils.jwt_helper import create_token
from utils.auth_dependency import get_current_user
from ai_engine.intelligence.face_engine import get_face_engine, calibrated_confidence
from ai_engine.intelligence.face_config import MATCH_THRESHOLD_STRICT

logger = logging.getLogger("face_auth")
router = APIRouter()

STORAGE_USERS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "storage", "users"
)
os.makedirs(STORAGE_USERS_DIR, exist_ok=True)


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class FaceRegisterWebcamRequest(BaseModel):
    name: str
    email: Optional[str] = None
    role: Optional[str] = "operator"
    image_base64: str


class FaceLoginWebcamRequest(BaseModel):
    image_base64: str


class AuthUserResponse(BaseModel):
    user_id: str
    name: str
    email: Optional[str] = None
    role: str
    photo_url: Optional[str] = None
    token: Optional[str] = None
    confidence: Optional[float] = None
    cosine_score: Optional[float] = None


# ─── Helper Functions ─────────────────────────────────────────────────────────

def _decode_base64_image(image_base64: str) -> np.ndarray:
    """Decodes a base64 or data-URL encoded image string to OpenCV BGR numpy array."""
    if not image_base64:
        raise HTTPException(status_code=400, detail="Image data cannot be empty.")

    if "," in image_base64:
        image_base64 = image_base64.split(",", 1)[1]

    try:
        raw_bytes = base64.b64decode(image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image encoding.")

    nparr = np.frombuffer(raw_bytes, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_bgr is None or img_bgr.size == 0:
        raise HTTPException(status_code=400, detail="Failed to decode image from camera capture.")

    return img_bgr


def _check_duplicate_face(db: Session, face_engine, new_embedding: np.ndarray, threshold: float = 0.45):
    """Compares new face embedding against all active users to ensure uniqueness."""
    active_users = db.query(User).filter(User.is_active == True).all()
    for u in active_users:
        for emb_rec in u.embeddings:
            try:
                vec = np.array(json.loads(emb_rec.embedding_json), dtype=np.float32)
                score = face_engine.compare_faces(new_embedding, vec)
                if score >= threshold:
                    logger.warning(f"[FaceAuth] Duplicate face detected: matches '{u.name}' with score {score:.3f}")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"This face is already registered in the system under the name '{u.name}'. "
                               f"Please log in or contact an administrator."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"[FaceAuth] Error comparing embedding for user {u.id}: {e}")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register-webcam", response_model=AuthUserResponse)
def register_with_webcam(
    data: FaceRegisterWebcamRequest,
    db: Session = Depends(get_db)
):
    """
    Registers a new system user directly from a webcam frame (base64).
    1. Validates face presence & quality using OpenCV YuNet quality gate.
    2. Extracts SFace 128-D embedding.
    3. Enforces face uniqueness across all registered users.
    4. Persists user, saves avatar image, and returns signed JWT token.
    """
    name_clean = data.name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Operator name cannot be empty.")

    email_clean = data.email.strip() if data.email else None
    if email_clean:
        existing = db.query(User).filter(User.email == email_clean).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Email '{email_clean}' is already registered.")

    img_bgr = _decode_base64_image(data.image_base64)
    face_engine = get_face_engine()

    success, embedding, error_msg, quality_score = face_engine.process_registration_image(img_bgr, run_quality_gate=True)
    if not success or embedding is None:
        raise HTTPException(
            status_code=400,
            detail=error_msg or "No clear front-facing face detected. Please ensure good lighting and face the camera directly."
        )

    # Prevent identity duplication
    _check_duplicate_face(db, face_engine, embedding, threshold=0.45)

    user_id = str(uuid.uuid4())
    photo_filename = f"{user_id}.jpg"
    photo_abs = os.path.join(STORAGE_USERS_DIR, photo_filename)
    photo_url = f"/api/auth/users/{user_id}/photo"

    # Save photo to disk
    cv2.imwrite(photo_abs, img_bgr)

    now = datetime.utcnow()
    user = User(
        id=user_id,
        name=name_clean,
        email=email_clean,
        role=data.role if data.role in ("admin", "operator", "viewer") else "operator",
        is_active=True,
        photo_path=photo_url,
        created_at=now,
        last_login_at=now,
    )
    db.add(user)
    db.flush()

    emb_record = UserFaceEmbedding(
        id=str(uuid.uuid4()),
        user_id=user.id,
        embedding_json=json.dumps(embedding.tolist()),
        created_at=now,
    )
    db.add(emb_record)
    db.commit()

    token = create_token(user.id, user.role, user.name)
    logger.info(f"[FaceAuth] Successfully registered new user '{user.name}' ({user.id}) with quality {quality_score}")

    return AuthUserResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        photo_url=user.photo_path,
        token=token,
    )


@router.post("/register", response_model=AuthUserResponse)
async def register_with_file(
    name: str = Form(...),
    email: Optional[str] = Form(None),
    role: Optional[str] = Form("operator"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Multipart file upload alternative for user registration."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Operator name cannot be empty.")

    email_clean = email.strip() if email else None
    if email_clean:
        existing = db.query(User).filter(User.email == email_clean).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Email '{email_clean}' is already registered.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None or img_bgr.size == 0:
        raise HTTPException(status_code=400, detail="Invalid image file format.")

    face_engine = get_face_engine()
    success, embedding, error_msg, quality_score = face_engine.process_registration_image(img_bgr, run_quality_gate=True)
    if not success or embedding is None:
        raise HTTPException(
            status_code=400,
            detail=error_msg or "No clear front-facing face detected."
        )

    _check_duplicate_face(db, face_engine, embedding, threshold=0.45)

    user_id = str(uuid.uuid4())
    photo_filename = f"{user_id}.jpg"
    photo_abs = os.path.join(STORAGE_USERS_DIR, photo_filename)
    photo_url = f"/api/auth/users/{user_id}/photo"

    with open(photo_abs, "wb") as f:
        f.write(contents)

    now = datetime.utcnow()
    user = User(
        id=user_id,
        name=name_clean,
        email=email_clean,
        role=role if role in ("admin", "operator", "viewer") else "operator",
        is_active=True,
        photo_path=photo_url,
        created_at=now,
        last_login_at=now,
    )
    db.add(user)
    db.flush()

    emb_record = UserFaceEmbedding(
        id=str(uuid.uuid4()),
        user_id=user.id,
        embedding_json=json.dumps(embedding.tolist()),
        created_at=now,
    )
    db.add(emb_record)
    db.commit()

    token = create_token(user.id, user.role, user.name)
    return AuthUserResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        photo_url=user.photo_path,
        token=token,
    )


@router.post("/login-webcam", response_model=AuthUserResponse)
def login_with_webcam(
    data: FaceLoginWebcamRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticates a user via face scan from webcam.
    1. Detects primary face in frame.
    2. Extracts SFace 128-D vector.
    3. Compares against all active registered users.
    4. If cosine >= 0.45, returns signed JWT and user session.
    """
    img_bgr = _decode_base64_image(data.image_base64)
    face_engine = get_face_engine()

    face = face_engine.detect_primary_face(img_bgr, score_threshold=0.50)
    if face is None:
        raise HTTPException(
            status_code=400,
            detail="No face detected in camera frame. Please look directly into the camera."
        )

    embedding = face_engine.extract_embedding(img_bgr, face)
    if embedding is None:
        raise HTTPException(
            status_code=400,
            detail="Failed to extract facial biometric features. Please adjust your position or lighting."
        )

    active_users = db.query(User).filter(User.is_active == True).all()
    if not active_users:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No registered users found in system. Please register first."
        )

    best_user = None
    best_score = -1.0

    for u in active_users:
        for emb_rec in u.embeddings:
            try:
                vec = np.array(json.loads(emb_rec.embedding_json), dtype=np.float32)
                score = face_engine.compare_faces(embedding, vec)
                if score > best_score:
                    best_score = score
                    best_user = u
            except Exception as e:
                logger.warning(f"[FaceAuth] Error parsing user embedding {emb_rec.id}: {e}")

    # Decision threshold: 0.45 cosine similarity
    THRESHOLD = 0.45
    if best_user and best_score >= THRESHOLD:
        best_user.last_login_at = datetime.utcnow()
        db.commit()

        token = create_token(best_user.id, best_user.role, best_user.name)
        cal_conf = calibrated_confidence(best_score)

        logger.info(f"[FaceAuth] Login SUCCESS for '{best_user.name}' (score: {best_score:.4f}, confidence: {cal_conf:.1f}%)")
        return AuthUserResponse(
            user_id=best_user.id,
            name=best_user.name,
            email=best_user.email,
            role=best_user.role,
            photo_url=best_user.photo_path,
            token=token,
            confidence=round(cal_conf, 1),
            cosine_score=round(best_score, 4),
        )

    logger.info(f"[FaceAuth] Login REJECTED (best cosine score: {best_score:.4f} < {THRESHOLD})")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Face not recognized. Access denied. Please ensure your face is enrolled and well-lit."
    )


@router.post("/login", response_model=AuthUserResponse)
async def login_with_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Multipart upload alternative for face login."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file submitted.")

    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None or img_bgr.size == 0:
        raise HTTPException(status_code=400, detail="Invalid image file.")

    face_engine = get_face_engine()
    face = face_engine.detect_primary_face(img_bgr, score_threshold=0.50)
    if face is None:
        raise HTTPException(status_code=400, detail="No face detected in probe image.")

    embedding = face_engine.extract_embedding(img_bgr, face)
    if embedding is None:
        raise HTTPException(status_code=400, detail="Failed to extract facial features.")

    active_users = db.query(User).filter(User.is_active == True).all()
    best_user = None
    best_score = -1.0

    for u in active_users:
        for emb_rec in u.embeddings:
            try:
                vec = np.array(json.loads(emb_rec.embedding_json), dtype=np.float32)
                score = face_engine.compare_faces(embedding, vec)
                if score > best_score:
                    best_score = score
                    best_user = u
            except Exception:
                pass

    if best_user and best_score >= 0.45:
        best_user.last_login_at = datetime.utcnow()
        db.commit()
        token = create_token(best_user.id, best_user.role, best_user.name)
        cal_conf = calibrated_confidence(best_score)
        return AuthUserResponse(
            user_id=best_user.id,
            name=best_user.name,
            email=best_user.email,
            role=best_user.role,
            photo_url=best_user.photo_path,
            token=token,
            confidence=round(cal_conf, 1),
            cosine_score=round(best_score, 4),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Face not recognized. Access denied."
    )


@router.get("/me", response_model=AuthUserResponse)
def get_me(user: User = Depends(get_current_user)):
    """Returns profile of currently authenticated user from Bearer JWT token."""
    return AuthUserResponse(
        user_id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        photo_url=user.photo_path,
    )


@router.get("/users/{user_id}/photo")
def get_user_photo(user_id: str, db: Session = Depends(get_db)):
    """Serves the enrolled photo of a user."""
    photo_abs = os.path.join(STORAGE_USERS_DIR, f"{user_id}.jpg")
    if not os.path.isfile(photo_abs):
        raise HTTPException(status_code=404, detail="User photo not found.")
    return FileResponse(photo_abs)
