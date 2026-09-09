"""
IBVAP Face Engine — Real Face Detection & Watchlist Recognition
===============================================================
Powered by OpenCV Zoo YuNet (5-landmark face detector) and SFace (128-D feature extractor).
Runs 100% locally with zero cloud API dependencies.
"""
import os
import cv2
import numpy as np
import json
import time
import logging
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger("face_engine")


class FaceEngine:
    """
    Singleton Face Engine for IBVAP.
    Manages YuNet face detector and SFace recognizer models,
    processes person crops, computes embeddings, and evaluates matches against the Watchlist.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FaceEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, models_dir: Optional[str] = None):
        if self._initialized:
            return

        if models_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            candidates = [
                os.path.normpath(os.path.join(base_dir, "models")),
                os.path.normpath(os.path.join(base_dir, "..", "models")),
                os.path.normpath(os.path.join(os.getcwd(), "models")),
                os.path.normpath(r"C:\Users\thaku\OneDrive\Desktop\IBVAP\models"),
            ]
            models_dir = candidates[0]
            for c in candidates:
                if os.path.exists(c) and os.path.isdir(c):
                    models_dir = c
                    break

        self.yunet_path = os.path.normpath(os.path.join(models_dir, "face_detection_yunet_2023mar.onnx"))
        self.sface_path = os.path.normpath(os.path.join(models_dir, "face_recognition_sface_2021dec.onnx"))

        self.detector = None
        self.recognizer = None
        self.track_face_cache: Dict[str, dict] = {} # key: f"{camera_id}:{track_id}" -> {result, timestamp}
        self.cache_ttl_seconds = 2.5 # Re-verify identity periodically

        self._load_models()
        self._initialized = True

    def _load_models(self):
        """Loads YuNet and SFace ONNX models."""
        try:
            if not os.path.exists(self.yunet_path):
                raise FileNotFoundError(f"YuNet model missing at {self.yunet_path}")
            if not os.path.exists(self.sface_path):
                raise FileNotFoundError(f"SFace model missing at {self.sface_path}")

            # Initialize YuNet with default input size (will be updated dynamically per crop/frame)
            self.detector = cv2.FaceDetectorYN_create(
                model=self.yunet_path,
                config="",
                input_size=(320, 320),
                score_threshold=0.55,
                nms_threshold=0.3,
                top_k=5000
            )

            # Initialize SFace recognizer
            self.recognizer = cv2.FaceRecognizerSF_create(
                model=self.sface_path,
                config=""
            )

            logger.info(f"[FaceEngine] YuNet and SFace loaded successfully from {self.yunet_path}")
        except Exception as e:
            logger.error(f"[FaceEngine] Failed to load face models: {e}", exc_info=True)
            self.detector = None
            self.recognizer = None

    @property
    def is_ready(self) -> bool:
        return self.detector is not None and self.recognizer is not None

    def detect_primary_face(self, img_bgr: np.ndarray, score_threshold: float = 0.55) -> Optional[np.ndarray]:
        """
        Detects faces in img_bgr and returns the primary face landmarks array.
        Returns None if no face detected or face bounding box is too small (< 20px).
        """
        if not self.is_ready or img_bgr is None or img_bgr.size == 0:
            return None

        h, w = img_bgr.shape[:2]
        if h < 24 or w < 24:
            return None

        try:
            self.detector.setInputSize((w, h))
            self.detector.setScoreThreshold(score_threshold)
            _, faces = self.detector.detect(img_bgr)

            if faces is None or len(faces) == 0:
                return None

            # Filter valid faces (min width & height 16px)
            valid_faces = [f for f in faces if f[2] >= 16 and f[3] >= 16 and f[-1] >= score_threshold]
            if not valid_faces:
                return None

            # Return the largest / highest-confidence face
            best_face = max(valid_faces, key=lambda f: f[2] * f[3] * f[-1])
            return best_face
        except Exception as e:
            logger.warning(f"[FaceEngine] Error detecting face: {e}")
            return None

    def extract_embedding(self, img_bgr: np.ndarray, face_info: np.ndarray) -> Optional[np.ndarray]:
        """
        Aligns, crops, and extracts a normalized 128-D feature embedding.
        """
        if not self.is_ready or img_bgr is None or face_info is None:
            return None

        try:
            aligned_face = self.recognizer.alignCrop(img_bgr, face_info)
            if aligned_face is None or aligned_face.size == 0:
                return None

            raw_feat = self.recognizer.feature(aligned_face)
            if raw_feat is None:
                return None

            feat = raw_feat.flatten().astype(np.float32)
            norm = np.linalg.norm(feat)
            if norm > 0:
                feat = feat / norm

            return feat
        except Exception as e:
            logger.warning(f"[FaceEngine] Error extracting embedding: {e}")
            return None

    def process_registration_image(self, img_bgr: np.ndarray) -> Tuple[bool, Optional[np.ndarray], Optional[str]]:
        """
        Processes an operator-uploaded registration photo.
        Returns (success, embedding_vector, error_message).
        Rejects photo if no clear human face is detected.
        """
        if not self.is_ready:
            return False, None, "Face recognition models are not loaded on server."

        if img_bgr is None or img_bgr.size == 0:
            return False, None, "Invalid image file format or empty image."

        face = self.detect_primary_face(img_bgr, score_threshold=0.50)
        if face is None:
            return False, None, "No clear human face detected in the photo. Please provide a well-lit, front-facing image."

        embedding = self.extract_embedding(img_bgr, face)
        if embedding is None or len(embedding) != 128:
            return False, None, "Failed to generate face embedding from the photo."

        return True, embedding, None

    def match_against_watchlist(
        self,
        query_embedding: np.ndarray,
        watchlist_records: List[Dict[str, Any]],
        threshold: float = 0.45
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str], float, float]:
        """
        Compares query_embedding against active watchlist records.
        
        Args:
            query_embedding: 128-D float32 numpy array
            watchlist_records: list of dicts with keys:
                {'person_id', 'name', 'identifier', 'threat_priority', 'embedding': np.ndarray}
            threshold: Cosine similarity threshold (0.35 to 0.70, default 0.45)

        Returns:
            (is_match, person_id, name, identifier, threat_priority, similarity_pct, cosine_score)
        """
        if query_embedding is None or not watchlist_records:
            return False, None, None, None, None, 0.0, 0.0

        best_score = -1.0
        best_match = None

        q_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-7)

        for record in watchlist_records:
            t_emb = record.get("embedding")
            if t_emb is None:
                continue

            t_norm = t_emb / (np.linalg.norm(t_emb) + 1e-7)
            cosine = float(np.dot(q_norm, t_norm))

            if cosine > best_score:
                best_score = cosine
                best_match = record

        similarity_pct = round(max(0.0, min(100.0, (best_score * 100.0))), 1)

        if best_score >= threshold and best_match is not None:
            return (
                True,
                best_match["person_id"],
                best_match["name"],
                best_match.get("identifier"),
                best_match.get("threat_priority", "HIGH"),
                similarity_pct,
                round(best_score, 4)
            )

        return False, None, "UNKNOWN", None, None, similarity_pct, round(max(0.0, best_score), 4)

    def evaluate_person_track_face(
        self,
        frame_bgr: np.ndarray,
        person_bbox: Dict[str, float], # {"x", "y", "w", "h"} in %
        camera_id: str,
        track_id: Optional[int],
        watchlist_records: List[Dict[str, Any]],
        threshold: float = 0.45,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluates face recognition for a detected person track in a real frame.
        Caches track identity to avoid redundant face recognition on every single frame.
        """
        cache_key = f"{camera_id}:{track_id}" if track_id is not None else None
        now = time.time()

        if cache_key and not force_refresh:
            cached = self.track_face_cache.get(cache_key)
            if cached and (now - cached["timestamp"]) < self.cache_ttl_seconds:
                return cached["result"]

        # Crop person region from frame
        h, w = frame_bgr.shape[:2]
        x1 = max(0, int((person_bbox["x"] / 100.0) * w))
        y1 = max(0, int((person_bbox["y"] / 100.0) * h))
        pw = max(10, int((person_bbox["w"] / 100.0) * w))
        ph = max(10, int((person_bbox["h"] / 100.0) * h))
        x2 = min(w, x1 + pw)
        y2 = min(h, y1 + ph)

        # Upper body / head region focus (top 50% of person bounding box)
        head_y2 = min(h, y1 + int(ph * 0.55))
        person_head_crop = frame_bgr[y1:head_y2, x1:x2]

        if person_head_crop.size == 0:
            res = {"face_detected": False, "is_match": False, "person_name": None, "similarity": 0.0}
            return res

        face_info = self.detect_primary_face(person_head_crop, score_threshold=0.50)
        if face_info is None:
            # Fallback to full person crop if head crop missed angle
            full_crop = frame_bgr[y1:y2, x1:x2]
            face_info = self.detect_primary_face(full_crop, score_threshold=0.50)
            if face_info is not None:
                person_head_crop = full_crop

        if face_info is None:
            res = {"face_detected": False, "is_match": False, "person_name": None, "similarity": 0.0}
            if cache_key:
                self.track_face_cache[cache_key] = {"result": res, "timestamp": now}
            return res

        # Face detected -> compute embedding
        embedding = self.extract_embedding(person_head_crop, face_info)
        if embedding is None:
            res = {"face_detected": True, "is_match": False, "person_name": "UNKNOWN", "similarity": 0.0}
            if cache_key:
                self.track_face_cache[cache_key] = {"result": res, "timestamp": now}
            return res

        # Match against active watchlist
        is_match, pid, pname, ident, priority, sim_pct, cos_score = self.match_against_watchlist(
            embedding, watchlist_records, threshold=threshold
        )

        res = {
            "face_detected": True,
            "is_match": is_match,
            "person_id": pid,
            "person_name": pname if is_match else "UNKNOWN",
            "identifier": ident,
            "threat_priority": priority,
            "similarity": sim_pct,
            "cosine_score": cos_score
        }

        if cache_key:
            self.track_face_cache[cache_key] = {"result": res, "timestamp": now}

        return res

    def clear_cache(self):
        """Clears track face cache."""
        self.track_face_cache.clear()


# Global singleton instance helper
_global_face_engine = None

def get_face_engine() -> FaceEngine:
    global _global_face_engine
    if _global_face_engine is None:
        _global_face_engine = FaceEngine()
    return _global_face_engine
