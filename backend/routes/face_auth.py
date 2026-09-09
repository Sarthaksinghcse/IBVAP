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

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func
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
from utils.paths import get_storage_root
from ai_engine.intelligence.face_engine import get_face_engine, calibrated_confidence
from ai_engine.intelligence.face_config import SFACE_COSINE_THRESHOLD, MATCH_THRESHOLD_STRICT

logger = logging.getLogger("face_auth")
router = APIRouter()

# Unified persistent storage directory
STORAGE_ROOT = get_storage_root()
STORAGE_USERS_DIR = os.path.join(STORAGE_ROOT, "users")
os.makedirs(STORAGE_USERS_DIR, exist_ok=True)

# Calibrated webcam login cosine threshold (OpenCV SFace standard: 0.363)
LOGIN_THRESHOLD = 0.38
DUPLICATE_FACE_THRESHOLD = 0.45


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
    is_update: Optional[bool] = False


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


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register-webcam", response_model=AuthUserResponse)
def register_with_webcam(
    data: FaceRegisterWebcamRequest,
    db: Session = Depends(get_db)
):
    """
    Registers or updates an operator's biometric face credentials from webcam.
    1. Validates face presence & quality with low-light auto-enhancement.
    2. Extracts SFace 128-D embedding representation.
    3. Handles both first-time enrollment and existing operator profile updates
       (multi-embedding bank) cleanly without artificial lockouts.
    4. Persists permanently to SQLite database and user avatar disk storage.
    """
    name_clean = data.name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Operator name cannot be empty.")

    email_clean = data.email.strip() if data.email else None
    img_bgr = _decode_base64_image(data.image_base64)
    face_engine = get_face_engine()

    # Pre-enhance low-light frames if needed
    img_bgr = face_engine._apply_low_light_enhancement(img_bgr)

    success, embedding, error_msg, quality_score = face_engine.process_registration_image(
        img_bgr, run_quality_gate=True
    )
    if not success or embedding is None:
        # Retry with force CLAHE enhancement if first pass failed
        enhanced = face_engine._apply_low_light_enhancement(img_bgr, luma=10.0)
        success, embedding, error_msg, quality_score = face_engine.process_registration_image(
            enhanced, run_quality_gate=False
        )
        if not success or embedding is None:
            raise HTTPException(
                status_code=400,
                detail=error_msg or "No clear front-facing face detected. Please ensure good lighting and face the camera directly."
            )

    now = datetime.utcnow()

    # Check for existing users to determine if this is an update / re-enrollment
    active_users = db.query(User).filter(User.is_active == True).all()
    matched_user_by_face = None
    best_face_score = -1.0

    for u in active_users:
        for emb_rec in u.embeddings:
            try:
                vec = np.array(json.loads(emb_rec.embedding_json), dtype=np.float32)
                score = face_engine.compare_faces(embedding, vec)
                if score > best_face_score:
                    best_face_score = score
                    if score >= DUPLICATE_FACE_THRESHOLD:
                        matched_user_by_face = u
            except Exception as e:
                logger.warning(f"[FaceAuth] Error parsing embedding for user {u.id}: {e}")

    # Also match by exact name or email
    user_by_name = db.query(User).filter(func.lower(User.name) == name_clean.lower(), User.is_active == True).first()
    user_by_email = db.query(User).filter(User.email == email_clean).first() if email_clean else None

    # Handle cross-identity conflict: Face belongs to another operator with a completely different name
    if matched_user_by_face and user_by_name and matched_user_by_face.id != user_by_name.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This face is already enrolled under '{matched_user_by_face.name}'. "
                   f"Please enter '{matched_user_by_face.name}' to update credentials or log in directly."
        )

    # Determine target user (update existing vs create new)
    target_user = matched_user_by_face or user_by_name or user_by_email
    is_update = target_user is not None

    if is_update:
        # Update existing operator profile & enrich biometric bank
        target_user.name = name_clean
        if email_clean:
            target_user.email = email_clean
        if data.role in ("admin", "operator", "viewer"):
            target_user.role = data.role
        target_user.last_login_at = now

        photo_filename = f"{target_user.id}.jpg"
        photo_abs = os.path.join(STORAGE_USERS_DIR, photo_filename)
        cv2.imwrite(photo_abs, img_bgr)
        target_user.photo_path = f"/api/auth/users/{target_user.id}/photo"

        # Append new embedding vector
        new_emb = UserFaceEmbedding(
            id=str(uuid.uuid4()),
            user_id=target_user.id,
            embedding_json=json.dumps(embedding.tolist()),
            created_at=now,
        )
        db.add(new_emb)
        db.flush()

        # Keep up to 5 most recent diverse embeddings to maximize recognition accuracy
        all_embs = db.query(UserFaceEmbedding).filter(
            UserFaceEmbedding.user_id == target_user.id
        ).order_by(UserFaceEmbedding.created_at.desc()).all()
        if len(all_embs) > 5:
            for old_emb in all_embs[5:]:
                db.delete(old_emb)

        db.commit()
        db.refresh(target_user)
        user_record = target_user
        logger.info(f"[FaceAuth] Successfully re-enrolled/updated operator '{user_record.name}' ({user_record.id}). Total embeddings: {min(len(all_embs), 5)}")
    else:
        # Create brand new operator
        user_id = str(uuid.uuid4())
        photo_filename = f"{user_id}.jpg"
        photo_abs = os.path.join(STORAGE_USERS_DIR, photo_filename)
        photo_url = f"/api/auth/users/{user_id}/photo"

        # Save photo to disk
        cv2.imwrite(photo_abs, img_bgr)

        new_user = User(
            id=user_id,
            name=name_clean,
            email=email_clean,
            role=data.role if data.role in ("admin", "operator", "viewer") else "operator",
            is_active=True,
            photo_path=photo_url,
            created_at=now,
            last_login_at=now,
        )
        db.add(new_user)
        db.flush()

        emb_record = UserFaceEmbedding(
            id=str(uuid.uuid4()),
            user_id=new_user.id,
            embedding_json=json.dumps(embedding.tolist()),
            created_at=now,
        )
        db.add(emb_record)
        db.commit()
        db.refresh(new_user)
        user_record = new_user
        logger.info(f"[FaceAuth] Successfully registered new operator '{user_record.name}' ({user_record.id}) with quality {quality_score}")

    token = create_token(user_record.id, user_record.role, user_record.name)

    return AuthUserResponse(
        user_id=user_record.id,
        name=user_record.name,
        email=user_record.email,
        role=user_record.role,
        photo_url=user_record.photo_path,
        token=token,
        is_update=is_update,
    )


@router.post("/register", response_model=AuthUserResponse)
async def register_with_file(
    name: str = Form(...),
    email: Optional[str] = Form(None),
    role: Optional[str] = Form("operator"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Multipart file upload alternative for operator registration/re-enrollment."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Operator name cannot be empty.")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None or img_bgr.size == 0:
        raise HTTPException(status_code=400, detail="Invalid image file format.")

    # Forward to webcam registration flow logic
    _, encoded = cv2.imencode(".jpg", img_bgr)
    b64_str = base64.b64encode(encoded).decode("utf-8")
    return register_with_webcam(
        FaceRegisterWebcamRequest(name=name_clean, email=email, role=role, image_base64=b64_str),
        db=db
    )


@router.post("/login-webcam", response_model=AuthUserResponse)
def login_with_webcam(
    data: FaceLoginWebcamRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticates an operator via face scan from webcam.
    1. Pre-enhances image for low-light invariance.
    2. Detects face with dual-threshold fallback.
    3. Extracts SFace 128-D biometric signature.
    4. Compares against all active registered users across all their embeddings.
    5. At cosine similarity >= 0.38, issues signed JWT session.
    """
    img_bgr = _decode_base64_image(data.image_base64)
    face_engine = get_face_engine()

    # Low-light enhancement
    img_bgr = face_engine._apply_low_light_enhancement(img_bgr)

    # Detect face (with fallback threshold)
    face = face_engine.detect_primary_face(img_bgr, score_threshold=0.45)
    if face is None:
        face = face_engine.detect_primary_face(img_bgr, score_threshold=0.35)
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
            detail="No registered operators found in database. Please enroll your face first."
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

    if best_user and best_score >= LOGIN_THRESHOLD:
        best_user.last_login_at = datetime.utcnow()

        # Adaptive learning: if match is high confidence and user has < 5 embeddings, store this angle
        if best_score >= 0.50 and len(best_user.embeddings) < 5:
            try:
                adaptive_emb = UserFaceEmbedding(
                    id=str(uuid.uuid4()),
                    user_id=best_user.id,
                    embedding_json=json.dumps(embedding.tolist()),
                    created_at=datetime.utcnow(),
                )
                db.add(adaptive_emb)
            except Exception as e:
                logger.warning(f"[FaceAuth] Adaptive embedding save skipped: {e}")

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

    logger.info(f"[FaceAuth] Login REJECTED (best cosine score: {best_score:.4f} < {LOGIN_THRESHOLD})")
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

    _, encoded = cv2.imencode(".jpg", img_bgr)
    b64_str = base64.b64encode(encoded).decode("utf-8")
    return login_with_webcam(FaceLoginWebcamRequest(image_base64=b64_str), db=db)


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


@router.get("/status")
def get_auth_status(db: Session = Depends(get_db)):
    """Diagnostic endpoint reporting registered operator count and persistence status."""
    active_users = db.query(User).filter(User.is_active == True).all()
    return {
        "status": "ONLINE",
        "registered_operators": len(active_users),
        "operators": [
            {
                "id": u.id,
                "name": u.name,
                "role": u.role,
                "embeddings_count": len(u.embeddings),
                "has_photo": os.path.isfile(os.path.join(STORAGE_USERS_DIR, f"{u.id}.jpg")),
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            }
            for u in active_users
        ],
        "storage_users_dir": STORAGE_USERS_DIR,
        "login_threshold": LOGIN_THRESHOLD,
    }

