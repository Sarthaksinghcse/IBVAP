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
import threading
import logging
from collections import defaultdict, deque
from typing import List, Dict, Optional, Tuple, Any

from ai_engine.intelligence.face_config import (
    SFACE_COSINE_THRESHOLD,
    MATCH_THRESHOLD_STRICT,
    MATCH_THRESHOLD_LENIENT,
    MIN_FACE_PX,
    MIN_FACE_ENROLL_PX,
    FACE_DETECT_SCORE,
    FACE_DETECT_SCORE_REG,
    NEG_CACHE_TTL_S,
    POS_CACHE_TTL_S,
    MAX_CACHE_ENTRIES,
    AMBIGUITY_MARGIN,
    TOP_K_CANDIDATES,
    CONSENSUS_WINDOW_SIZE,
    CONSENSUS_CONFIRM_MIN,
    CONSENSUS_CONFIRM_WINDOW,
    CONSENSUS_CANDIDATE_MIN,
    QUALITY_LAPLACIAN_MIN,
    QUALITY_LUMA_MIN,
    QUALITY_LUMA_MAX,
    QUALITY_POSE_RATIO_MIN,
    QUALITY_POSE_RATIO_MAX,
    LOW_LIGHT_LUMA_THRESHOLD,
    LOW_LIGHT_CLAHE_CLIP,
    LOW_LIGHT_CLAHE_GRID,
    CALIBRATION_THRESHOLD_COSINE,
    CALIBRATION_THRESHOLD_DISPLAY,
    CALIBRATION_GENUINE_COSINE,
    CALIBRATION_GENUINE_DISPLAY,
)

logger = logging.getLogger("face_engine")


# ─── Temporal Consensus Accumulator (Phase 4.1) ──────────────────────────────

class FaceTrackAccumulator:
    """
    Per-track deque holding the last N per-frame face recognition results.
    Confirms a match only when the same person_id wins >= CONSENSUS_CONFIRM_MIN
    of the last CONSENSUS_CONFIRM_WINDOW evaluations. Reports median similarity.
    Emits CANDIDATE at CONSENSUS_CANDIDATE_MIN hits.
    """

    def __init__(self):
        # key: job-scoped cache key -> deque of result dicts
        self._tracks: Dict[str, deque] = {}

    def push(self, cache_key: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Push a raw per-frame result and return the consensus-adjusted result.
        """
        if cache_key not in self._tracks:
            self._tracks[cache_key] = deque(maxlen=CONSENSUS_WINDOW_SIZE)

        self._tracks[cache_key].append(result)
        window = list(self._tracks[cache_key])

        # Only consider the last CONSENSUS_CONFIRM_WINDOW entries
        recent = window[-CONSENSUS_CONFIRM_WINDOW:]

        # Count person_id votes among matches
        votes: Dict[Optional[str], int] = defaultdict(int)
        similarities: Dict[Optional[str], list] = defaultdict(list)

        for r in recent:
            if r.get("is_match") and r.get("person_id"):
                pid = r["person_id"]
                votes[pid] += 1
                similarities[pid].append(r.get("cosine_score", 0.0))

        if not votes:
            # No matches in window — pass through the raw result
            return result

        best_pid = max(votes, key=votes.get)
        best_count = votes[best_pid]

        if best_count >= CONSENSUS_CONFIRM_MIN:
            # Confirmed match — report median similarity
            sims = sorted(similarities[best_pid])
            median_sim = sims[len(sims) // 2]
            # Find the most recent result for this person to get metadata
            for r in reversed(recent):
                if r.get("person_id") == best_pid:
                    confirmed = dict(r)
                    confirmed["cosine_score"] = round(median_sim, 4)
                    confirmed["similarity"] = round(max(0.0, min(100.0, median_sim * 100.0)), 1)
                    confirmed["consensus_state"] = "CONFIRMED"
                    confirmed["consensus_votes"] = best_count
                    return confirmed
        elif best_count >= CONSENSUS_CANDIDATE_MIN:
            # Candidate — show in UI, don't alert
            for r in reversed(recent):
                if r.get("person_id") == best_pid:
                    candidate = dict(r)
                    candidate["is_match"] = False  # Don't trigger alert
                    candidate["consensus_state"] = "CANDIDATE"
                    candidate["consensus_votes"] = best_count
                    return candidate

        return result

    def clear_scope(self, prefix: str):
        """Remove all entries whose key starts with prefix."""
        keys_to_del = [k for k in self._tracks if k.startswith(prefix)]
        for k in keys_to_del:
            del self._tracks[k]

    def clear(self):
        self._tracks.clear()


# ─── Calibrated Confidence (Phase 4.4) ───────────────────────────────────────

def calibrated_confidence(cosine_score: float) -> float:
    """
    Piecewise-linear calibration so the decision threshold maps to ~50%
    and the genuine-pair median maps to ~95%.
    Raw cosine is kept in DB; this is for display only.
    """
    if cosine_score <= 0.0:
        return 0.0

    if cosine_score <= CALIBRATION_THRESHOLD_COSINE:
        # Linear from 0→0% to threshold→50%
        return (cosine_score / CALIBRATION_THRESHOLD_COSINE) * CALIBRATION_THRESHOLD_DISPLAY
    elif cosine_score <= CALIBRATION_GENUINE_COSINE:
        # Linear from threshold→50% to genuine→95%
        span_cosine = CALIBRATION_GENUINE_COSINE - CALIBRATION_THRESHOLD_COSINE
        span_display = CALIBRATION_GENUINE_DISPLAY - CALIBRATION_THRESHOLD_DISPLAY
        t = (cosine_score - CALIBRATION_THRESHOLD_COSINE) / span_cosine
        return CALIBRATION_THRESHOLD_DISPLAY + t * span_display
    else:
        # Linear from genuine→95% to 1.0→100%
        span_cosine = 1.0 - CALIBRATION_GENUINE_COSINE
        span_display = 100.0 - CALIBRATION_GENUINE_DISPLAY
        t = (cosine_score - CALIBRATION_GENUINE_COSINE) / span_cosine
        return min(100.0, CALIBRATION_GENUINE_DISPLAY + t * span_display)


# ─── Face Engine ──────────────────────────────────────────────────────────────

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
            models_dir = os.path.join(base_dir, "models")

        self.yunet_path = os.path.normpath(os.path.join(models_dir, "face_detection_yunet_2023mar.onnx"))
        self.sface_path = os.path.normpath(os.path.join(models_dir, "face_recognition_sface_2021dec.onnx"))

        self.detector = None
        self.recognizer = None
        self.track_face_cache: Dict[str, dict] = {} # key: f"{job_id}:{camera_id}:{track_id}" -> {result, timestamp}

        # Phase 0.4: Thread lock for non-thread-safe OpenCV native state (C3)
        self._lock = threading.Lock()

        # Phase 4.1: Temporal consensus accumulator
        self._accumulator = FaceTrackAccumulator()

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

    def _apply_low_light_enhancement(self, img_bgr: np.ndarray) -> np.ndarray:
        """
        Phase 4.6: If mean frame luma is below threshold, apply CLAHE enhancement.
        Reuses the same CLAHE approach proven in anpr_engine.py.
        """
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        mean_luma = float(np.mean(gray))
        if mean_luma < LOW_LIGHT_LUMA_THRESHOLD:
            clahe = cv2.createCLAHE(clipLimit=LOW_LIGHT_CLAHE_CLIP, tileGridSize=LOW_LIGHT_CLAHE_GRID)
            lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            l_channel = clahe.apply(l_channel)
            enhanced = cv2.merge([l_channel, a_channel, b_channel])
            return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        return img_bgr

    def detect_primary_face(self, img_bgr: np.ndarray, score_threshold: float = FACE_DETECT_SCORE) -> Optional[np.ndarray]:
        """
        Detects faces in img_bgr and returns the primary face landmarks array.
        Returns None if no face detected or face bounding box is too small.
        Thread-safe via self._lock (Phase 0.4 — C3).
        """
        if not self.is_ready or img_bgr is None or img_bgr.size == 0:
            return None

        h, w = img_bgr.shape[:2]
        if h < 24 or w < 24:
            return None

        try:
            # Phase 0.4: Lock the set-size → detect sequence as one critical section
            with self._lock:
                self.detector.setInputSize((w, h))
                self.detector.setScoreThreshold(score_threshold)
                _, faces = self.detector.detect(img_bgr)

            if faces is None or len(faces) == 0:
                return None

            # Filter valid faces (min width & height from config)
            valid_faces = [f for f in faces if f[2] >= MIN_FACE_PX and f[3] >= MIN_FACE_PX and f[-1] >= score_threshold]
            if not valid_faces:
                return None

            # Return the largest / highest-confidence face
            best_face = max(valid_faces, key=lambda f: f[2] * f[3] * f[-1])
            return best_face
        except Exception as e:
            logger.warning(f"[FaceEngine] Error detecting face: {e}")
            return None

    def detect_all_faces(self, img_bgr: np.ndarray, score_threshold: float = FACE_DETECT_SCORE) -> List[np.ndarray]:
        """
        Detects ALL faces in img_bgr. Used by quality gate to check uniqueness.
        """
        if not self.is_ready or img_bgr is None or img_bgr.size == 0:
            return []

        h, w = img_bgr.shape[:2]
        if h < 24 or w < 24:
            return []

        try:
            with self._lock:
                self.detector.setInputSize((w, h))
                self.detector.setScoreThreshold(score_threshold)
                _, faces = self.detector.detect(img_bgr)

            if faces is None or len(faces) == 0:
                return []

            return [f for f in faces if f[2] >= MIN_FACE_PX and f[3] >= MIN_FACE_PX and f[-1] >= score_threshold]
        except Exception as e:
            logger.warning(f"[FaceEngine] Error detecting faces: {e}")
            return []

    def extract_embedding(self, img_bgr: np.ndarray, face_info: np.ndarray) -> Optional[np.ndarray]:
        """
        Aligns, crops, and extracts a normalized 128-D feature embedding.
        Thread-safe via self._lock (Phase 0.4).
        """
        if not self.is_ready or img_bgr is None or face_info is None:
            return None

        try:
            with self._lock:
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

    # ─── Phase 3.2: Quality Gate ──────────────────────────────────────────────

    def assess_quality(self, img_bgr: np.ndarray, face_info: np.ndarray) -> Tuple[bool, float, str]:
        """
        Phase 3.2: Enrollment quality gate. Rejects bad enrollments.

        Checks:
          - Face size >= 80x80 px
          - Sharpness: Laplacian variance >= 60
          - Brightness: mean luma within [50, 205]
          - Pose: landmark symmetry ratio within [0.65, 1.55]
          - Uniqueness: exactly 1 face in photo

        Returns: (ok, quality_score, reason)
        """
        if face_info is None:
            return False, 0.0, "No face detected in the photo."

        face_w, face_h = float(face_info[2]), float(face_info[3])
        score = 0.0

        # 1. Face size check
        if face_w < MIN_FACE_ENROLL_PX or face_h < MIN_FACE_ENROLL_PX:
            return False, 10.0, f"Face too small ({int(face_w)}x{int(face_h)}px). Minimum is {MIN_FACE_ENROLL_PX}x{MIN_FACE_ENROLL_PX}px."
        size_score = min(25.0, (face_w * face_h) / (MIN_FACE_ENROLL_PX * MIN_FACE_ENROLL_PX) * 12.5)
        score += size_score

        # 2. Sharpness (Laplacian variance on face region)
        fx, fy = int(face_info[0]), int(face_info[1])
        fw, fh = int(face_info[2]), int(face_info[3])
        h, w = img_bgr.shape[:2]
        fx1, fy1 = max(0, fx), max(0, fy)
        fx2, fy2 = min(w, fx + fw), min(h, fy + fh)
        face_crop = img_bgr[fy1:fy2, fx1:fx2]

        if face_crop.size == 0:
            return False, score, "Could not extract face region."

        gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray_face, cv2.CV_64F).var()

        if laplacian_var < QUALITY_LAPLACIAN_MIN:
            return False, score + 5.0, f"Image too blurry (sharpness: {laplacian_var:.1f}, minimum: {QUALITY_LAPLACIAN_MIN})."
        sharp_score = min(25.0, (laplacian_var / QUALITY_LAPLACIAN_MIN) * 12.5)
        score += sharp_score

        # 3. Brightness check
        mean_luma = float(np.mean(gray_face))
        if mean_luma < QUALITY_LUMA_MIN:
            return False, score + 5.0, f"Image too dark (brightness: {mean_luma:.0f}, minimum: {QUALITY_LUMA_MIN})."
        if mean_luma > QUALITY_LUMA_MAX:
            return False, score + 5.0, f"Image too bright/overexposed (brightness: {mean_luma:.0f}, maximum: {QUALITY_LUMA_MAX})."
        # Score brightness based on distance from ideal center
        ideal_luma = (QUALITY_LUMA_MIN + QUALITY_LUMA_MAX) / 2.0
        luma_dist = abs(mean_luma - ideal_luma) / ideal_luma
        luma_score = max(5.0, 25.0 * (1.0 - luma_dist))
        score += luma_score

        # 4. Pose symmetry (landmark-based)
        # YuNet face_info: [x, y, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score]
        if len(face_info) >= 14:
            try:
                x_re, y_re = float(face_info[4]), float(face_info[5])   # Right eye
                x_le, y_le = float(face_info[6]), float(face_info[7])   # Left eye
                x_nt, y_nt = float(face_info[8]), float(face_info[9])   # Nose tip

                dist_r = np.sqrt((x_re - x_nt) ** 2 + (y_re - y_nt) ** 2)
                dist_l = np.sqrt((x_le - x_nt) ** 2 + (y_le - y_nt) ** 2)

                if dist_l > 0:
                    ratio = dist_r / dist_l
                    if ratio < QUALITY_POSE_RATIO_MIN or ratio > QUALITY_POSE_RATIO_MAX:
                        return False, score + 5.0, f"Face pose too extreme (symmetry ratio: {ratio:.2f}). Please use a front-facing photo."
                    # Score symmetry — 1.0 is perfect
                    sym_dev = abs(ratio - 1.0)
                    pose_score = max(5.0, 25.0 * (1.0 - sym_dev * 2.0))
                    score += pose_score
                else:
                    score += 15.0  # Can't compute — give partial credit
            except (IndexError, ValueError):
                score += 15.0  # Landmark extraction failed — give partial credit
        else:
            score += 15.0

        # 5. Uniqueness — exactly 1 face
        all_faces = self.detect_all_faces(img_bgr, score_threshold=FACE_DETECT_SCORE_REG)
        if len(all_faces) > 1:
            return False, score, f"Multiple faces detected ({len(all_faces)}). Please provide a photo with exactly one person."

        score = round(min(100.0, score), 1)
        return True, score, "Quality check passed."

    def process_registration_image(self, img_bgr: np.ndarray, run_quality_gate: bool = True) -> Tuple[bool, Optional[np.ndarray], Optional[str], float]:
        """
        Processes an operator-uploaded registration photo.
        Returns (success, embedding_vector, error_message, quality_score).
        Rejects photo if no clear human face is detected or quality gate fails.
        """
        if not self.is_ready:
            return False, None, "Face recognition models are not loaded on server.", 0.0

        if img_bgr is None or img_bgr.size == 0:
            return False, None, "Invalid image file format or empty image.", 0.0

        face = self.detect_primary_face(img_bgr, score_threshold=FACE_DETECT_SCORE_REG)
        if face is None:
            return False, None, "No clear human face detected in the photo. Please provide a well-lit, front-facing image.", 0.0

        # Phase 3.2: Quality gate
        quality_score = 0.0
        if run_quality_gate:
            ok, quality_score, reason = self.assess_quality(img_bgr, face)
            if not ok:
                return False, None, reason, quality_score

        embedding = self.extract_embedding(img_bgr, face)
        if embedding is None or len(embedding) != 128:
            return False, None, "Failed to generate face embedding from the photo.", quality_score

        return True, embedding, None, quality_score

    def match_against_watchlist(
        self,
        query_embedding: np.ndarray,
        watchlist_records: List[Dict[str, Any]],
        threshold: float = MATCH_THRESHOLD_STRICT
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str], float, float, List[Dict[str, Any]]]:
        """
        Phase 3.4: Multi-embedding grouped matching.

        Groups records by person_id. Per person, score = max cosine across their embeddings.
        Requires 2nd-best person to trail by AMBIGUITY_MARGIN, else returns AMBIGUOUS.
        Returns top-K candidates for operator review.

        Returns:
            (is_match, person_id, name, identifier, threat_priority,
             similarity_pct, cosine_score, top_candidates)
        """
        empty_result = (False, None, None, None, None, 0.0, 0.0, [])
        if query_embedding is None or not watchlist_records:
            return empty_result

        q_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-7)

        # Group embeddings by person_id and compute max cosine per person
        person_scores: Dict[str, Dict[str, Any]] = {}

        for record in watchlist_records:
            t_emb = record.get("embedding")
            if t_emb is None:
                continue

            t_norm = t_emb / (np.linalg.norm(t_emb) + 1e-7)
            cosine = float(np.dot(q_norm, t_norm))
            pid = record["person_id"]

            if pid not in person_scores or cosine > person_scores[pid]["cosine"]:
                person_scores[pid] = {
                    "cosine": cosine,
                    "person_id": pid,
                    "name": record.get("name"),
                    "identifier": record.get("identifier"),
                    "threat_priority": record.get("threat_priority", "HIGH"),
                }

        if not person_scores:
            return empty_result

        # Sort by cosine descending
        sorted_persons = sorted(person_scores.values(), key=lambda x: x["cosine"], reverse=True)

        # Build top-K candidates list
        top_candidates = []
        for p in sorted_persons[:TOP_K_CANDIDATES]:
            cal_conf = calibrated_confidence(p["cosine"])
            top_candidates.append({
                "person_id": p["person_id"],
                "name": p["name"],
                "identifier": p["identifier"],
                "threat_priority": p["threat_priority"],
                "cosine_score": round(p["cosine"], 4),
                "similarity": round(max(0.0, min(100.0, p["cosine"] * 100.0)), 1),
                "calibrated_confidence": round(cal_conf, 1),
            })

        best = sorted_persons[0]
        best_score = best["cosine"]
        similarity_pct = round(max(0.0, min(100.0, best_score * 100.0)), 1)

        if best_score >= threshold:
            # Check ambiguity margin
            if len(sorted_persons) >= 2:
                second_score = sorted_persons[1]["cosine"]
                if (best_score - second_score) < AMBIGUITY_MARGIN:
                    # Ambiguous — two persons too close
                    return (
                        False, None, "AMBIGUOUS", None, None,
                        similarity_pct, round(best_score, 4), top_candidates
                    )

            return (
                True,
                best["person_id"],
                best["name"],
                best.get("identifier"),
                best.get("threat_priority", "HIGH"),
                similarity_pct,
                round(best_score, 4),
                top_candidates
            )

        return (False, None, "UNKNOWN", None, None, similarity_pct, round(max(0.0, best_score), 4), top_candidates)

    # ─── Cache Management (Phase 1.1) ────────────────────────────────────────

    def _evict_stale(self, now: float):
        """
        Phase 1.1: Evict stale cache entries.
        Cap at MAX_CACHE_ENTRIES, evict oldest-first.
        """
        if len(self.track_face_cache) <= MAX_CACHE_ENTRIES:
            return

        # Sort by timestamp, evict oldest until under cap
        sorted_keys = sorted(
            self.track_face_cache.keys(),
            key=lambda k: self.track_face_cache[k].get("timestamp", 0)
        )
        evict_count = len(self.track_face_cache) - MAX_CACHE_ENTRIES
        for key in sorted_keys[:evict_count]:
            del self.track_face_cache[key]

    def evaluate_person_track_face(
        self,
        frame_bgr: np.ndarray,
        person_bbox: Dict[str, float], # {"x", "y", "w", "h"} in %
        camera_id: str,
        track_id: Optional[int],
        watchlist_records: List[Dict[str, Any]],
        threshold: float = MATCH_THRESHOLD_STRICT,
        force_refresh: bool = False,
        job_id: str = "",
        now: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Evaluates face recognition for a detected person track in a real frame.
        Caches track identity to avoid redundant face recognition on every single frame.

        Phase 1.1 fixes: job-scoped cache key, explicit now parameter,
        negative caching with shorter TTL, bounded cache with eviction.
        Phase 4.1: Results pass through temporal consensus accumulator.
        Phase 4.6: Low-light CLAHE enhancement on head crop.
        """
        if now is None:
            now = time.time()

        # Phase 1.1: Job-scoped cache key (fixes C1 key collision)
        cache_key = f"{job_id}:{camera_id}:{track_id}" if track_id is not None else None

        # Phase 1.1: Evict stale entries
        self._evict_stale(now)

        if cache_key and not force_refresh:
            cached = self.track_face_cache.get(cache_key)
            if cached:
                cached_result = cached["result"]
                elapsed = now - cached["timestamp"]
                # Phase 1.1: Negative caching with shorter TTL
                if cached_result.get("face_detected"):
                    ttl = POS_CACHE_TTL_S
                else:
                    ttl = NEG_CACHE_TTL_S
                if elapsed < ttl:
                    return cached_result

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

        # Phase 4.6: Low-light enhancement
        person_head_crop = self._apply_low_light_enhancement(person_head_crop)

        face_info = self.detect_primary_face(person_head_crop, score_threshold=FACE_DETECT_SCORE)
        if face_info is None:
            # Fallback to full person crop if head crop missed angle
            full_crop = frame_bgr[y1:y2, x1:x2]
            full_crop = self._apply_low_light_enhancement(full_crop)
            face_info = self.detect_primary_face(full_crop, score_threshold=FACE_DETECT_SCORE)
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
        is_match, pid, pname, ident, priority, sim_pct, cos_score, top_candidates = self.match_against_watchlist(
            embedding, watchlist_records, threshold=threshold
        )

        cal_conf = calibrated_confidence(cos_score)

        res = {
            "face_detected": True,
            "is_match": is_match,
            "person_id": pid,
            "person_name": pname if is_match else "UNKNOWN",
            "identifier": ident,
            "threat_priority": priority,
            "similarity": sim_pct,
            "cosine_score": cos_score,
            "calibrated_confidence": round(cal_conf, 1),
            "top_candidates": top_candidates,
        }

        # Phase 4.1: Apply temporal consensus
        if cache_key:
            res = self._accumulator.push(cache_key, res)
            self.track_face_cache[cache_key] = {"result": res, "timestamp": now}

        return res

    def clear_cache(self):
        """Clears track face cache and consensus accumulator."""
        self.track_face_cache.clear()
        self._accumulator.clear()

    def clear_scope(self, prefix: str):
        """
        Phase 1.1: Clear cache entries for a specific job scope.
        Prevents cross-job identity leakage.
        """
        keys_to_del = [k for k in self.track_face_cache if k.startswith(prefix)]
        for k in keys_to_del:
            del self.track_face_cache[k]
        self._accumulator.clear_scope(prefix)


# Global singleton instance helper
_global_face_engine = None

def get_face_engine() -> FaceEngine:
    global _global_face_engine
    if _global_face_engine is None:
        _global_face_engine = FaceEngine()
    return _global_face_engine
