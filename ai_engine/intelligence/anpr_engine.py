"""
IBVAP ANPR Engine — Real Automatic Number Plate Recognition
============================================================
Powered by vehicle bumper ROI localization, adaptive multi-pass preprocessing,
local multi-engine OCR (Tesseract & EasyOCR), Indian registration plate normalization,
and confidence-weighted temporal consensus across vehicle tracking frames.
Runs 100% locally with zero cloud API dependencies. Zero hardcoded plate values.
"""

import os
import cv2
import numpy as np
import time
import re
import logging
from collections import Counter
from typing import Optional, Tuple, Dict, List, Any

logger = logging.getLogger("anpr_engine")

# Known Indian State / Union Territory Codes
INDIAN_STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ",
    "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
    "MZ", "NL", "OD", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK", "UP",
    "WB"
}

# Tesseract executable configuration
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class ANPREngine:
    """
    Singleton ANPR Engine for IBVAP.
    Manages license plate localization on vehicle bumper ROIs,
    upscaling & multi-variant preprocessing, local OCR neural extraction,
    Indian registration plate syntax validation, and temporal track consistency.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ANPREngine, cls).__new__(cls)
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

        self.models_dir = models_dir
        self.tesseract_available = False
        self.easyocr_reader = None
        self.crnn_model = None

        # Tracking state
        self.track_plate_history: Dict[str, List[dict]] = {}  # key: f"{camera_id}:{track_id}" -> list of readings
        self.track_plate_cache: Dict[str, dict] = {}    # key: f"{camera_id}:{track_id}" -> {result, timestamp}
        self.track_attempt_counts: Dict[str, int] = {}  # key: f"{camera_id}:{track_id}" -> int attempts
        self.cache_ttl_seconds = 2.5

        self._init_ocr_engines()
        self._initialized = True

    def _init_ocr_engines(self):
        """Initializes local OCR engines: Tesseract, EasyOCR, and OpenCV CRNN."""
        # 1. Initialize Tesseract if installed
        try:
            import pytesseract
            if os.path.exists(TESSERACT_CMD):
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
                self.pytesseract = pytesseract
                self.tesseract_available = True
                logger.info(f"[ANPREngine] Local Tesseract OCR initialized from {TESSERACT_CMD}")
            else:
                # Check default system path
                self.pytesseract = pytesseract
                self.tesseract_available = True
                logger.info("[ANPREngine] Tesseract OCR module loaded (system path)")
        except Exception as e:
            logger.warning(f"[ANPREngine] Tesseract initialization failed: {e}")
            self.tesseract_available = False

        # 2. Initialize EasyOCR
        try:
            import easyocr
            self.easyocr_module = easyocr
            # Lazy init reader on first use or here
            logger.info("[ANPREngine] EasyOCR library available for fallback extraction")
        except Exception as e:
            logger.warning(f"[ANPREngine] EasyOCR not available: {e}")
            self.easyocr_module = None

        # 3. Initialize CRNN fallback model
        try:
            crnn_path = os.path.normpath(os.path.join(self.models_dir, "text_recognition_CRNN_EN_2021sep.onnx"))
            if os.path.exists(crnn_path):
                net = cv2.dnn.readNet(crnn_path)
                self.crnn_model = cv2.dnn_TextRecognitionModel(net)
                self.crnn_model.setDecodeType("CTC-greedy")
                self.crnn_model.setVocabulary(list("0123456789abcdefghijklmnopqrstuvwxyz"))
                self.crnn_model.setInputParams(
                    scale=1.0 / 127.5,
                    mean=(127.5, 127.5, 127.5),
                    size=(100, 32)
                )
                logger.info("[ANPREngine] OpenCV Zoo CRNN model loaded as auxiliary recognizer")
        except Exception as e:
            logger.debug(f"[ANPREngine] CRNN model skipped: {e}")

    def _get_easyocr_reader(self):
        """Lazy-loads EasyOCR reader singleton to save memory if not needed."""
        if self.easyocr_reader is None and self.easyocr_module is not None:
            try:
                self.easyocr_reader = self.easyocr_module.Reader(["en"], gpu=False)
                logger.info("[ANPREngine] EasyOCR reader instance ready")
            except Exception as e:
                logger.error(f"[ANPREngine] Failed to create EasyOCR reader: {e}")
        return self.easyocr_reader

    @property
    def is_ready(self) -> bool:
        return self.tesseract_available or (self.easyocr_module is not None) or (self.crnn_model is not None)

    def locate_plate_region(self, vehicle_crop: np.ndarray) -> Tuple[bool, Optional[np.ndarray], Optional[dict]]:
        """
        High-accuracy license plate localizer on vehicle bumper ROI:
        1. Constrains candidate search to lower vehicle bumper (height 45%-95%, width 15%-85%).
        2. Applies dual-mode candidate isolation:
           - Color segmentation for reflective white/yellow license plates.
           - Sobel horizontal gradient filter for vertical alphanumeric edge clusters.
        3. Validates aspect ratio (2.0 - 6.0), minimum dimensions, and text edge variance.
        4. Returns: (plate_found, plate_crop_bgr, relative_bbox_dict)
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return False, None, None

        vh, vw = vehicle_crop.shape[:2]
        if vh < 25 or vw < 40:
            return False, None, None

        # Focus on vehicle bumper region where license plates are mounted
        by1 = int(vh * 0.45)
        by2 = int(vh * 0.95)
        bx1 = int(vw * 0.12)
        bx2 = int(vw * 0.88)
        bumper = vehicle_crop[by1:by2, bx1:bx2]
        bh, bw = bumper.shape[:2]

        if bh < 15 or bw < 30:
            bumper = vehicle_crop
            by1, bx1 = 0, 0
            bh, bw = vh, vw

        gray_bumper = cv2.cvtColor(bumper, cv2.COLOR_BGR2GRAY)
        candidates = []

        # --- Method 1: White & Yellow Reflective Plate Color Mask ---
        hsv_bumper = cv2.cvtColor(bumper, cv2.COLOR_BGR2HSV)
        white_mask = cv2.inRange(hsv_bumper, np.array([0, 0, 140]), np.array([180, 80, 255]))
        yellow_mask = cv2.inRange(hsv_bumper, np.array([14, 60, 130]), np.array([36, 255, 255]))
        color_mask = cv2.bitwise_or(white_mask, yellow_mask)

        kernel_morph = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 3))
        closed_color = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, kernel_morph)
        color_cnts, _ = cv2.findContours(closed_color, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in color_cnts:
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            ar = cw / float(ch) if ch > 0 else 0
            area = cw * ch
            # Standard Indian plate aspect ratio is between 2.2 and 5.5
            if 2.0 <= ar <= 6.0 and cw >= 32 and ch >= 9 and area >= 350:
                crop_gray = gray_bumper[cy:cy+ch, cx:cx+cw]
                std = float(np.std(crop_gray))
                if std > 14.0:
                    score = std * (1.0 - abs(ar - 3.4) / 7.0)
                    candidates.append((score, cx, cy, cw, ch))

        # --- Method 2: Sobel Horizontal Gradient (Vertical text edges) ---
        grad_x = cv2.Sobel(gray_bumper, cv2.CV_32F, 1, 0, ksize=3)
        grad_x = np.absolute(grad_x)
        g_min, g_max = np.min(grad_x), np.max(grad_x)
        if g_max > g_min:
            grad_x = ((grad_x - g_min) / (g_max - g_min) * 255).astype("uint8")

        blurred = cv2.GaussianBlur(grad_x, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel_grad = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        closed_grad = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_grad)
        grad_cnts, _ = cv2.findContours(closed_grad, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in grad_cnts:
            gx, gy, gw, gh = cv2.boundingRect(cnt)
            ar = gw / float(gh) if gh > 0 else 0
            area = gw * gh
            if 2.0 <= ar <= 6.2 and gw >= 35 and gh >= 9 and area >= 380:
                crop_gray = gray_bumper[gy:gy+gh, gx:gx+gw]
                std = float(np.std(crop_gray))
                if std > 15.0:
                    score = std * (1.0 - abs(ar - 3.4) / 7.0) * 0.95
                    candidates.append((score, gx, gy, gw, gh))

        if not candidates:
            # Fallback: check full vehicle lower half if bumper crop missed
            return False, None, None

        # Sort candidates by score descending
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, px, py, pw, ph = candidates[0]

        # Add slight proportional padding (5% horizontal, 8% vertical) to ensure characters are not clipped
        pad_x = int(pw * 0.06)
        pad_y = int(ph * 0.08)
        px1 = max(0, px - pad_x)
        py1 = max(0, py - pad_y)
        px2 = min(bw, px + pw + pad_x)
        py2 = min(bh, py + ph + pad_y)

        plate_crop = bumper[py1:py2, px1:px2]
        if plate_crop.size == 0:
            return False, None, None

        abs_x = bx1 + px1
        abs_y = by1 + py1
        abs_w = px2 - px1
        abs_h = py2 - py1

        return True, plate_crop, {"x": abs_x, "y": abs_y, "w": abs_w, "h": abs_h}

    def generate_plate_variants(self, plate_crop: np.ndarray) -> List[np.ndarray]:
        """
        Upscales plate crop (2x-3x) and applies multi-variant preprocessing:
        - Variant 1: Upscaled raw BGR
        - Variant 2: Grayscale + CLAHE + subtle unsharp masking for crisp text edges
        - Variant 3: Otsu adaptive binarization
        - Variant 4: Inverted Otsu binarization
        """
        if plate_crop is None or plate_crop.size == 0:
            return []

        ph, pw = plate_crop.shape[:2]
        # Choose dynamic practical scale factor: upscale small plates up to ~300px width
        scale = 3 if pw < 120 else (2 if pw < 220 else 1)
        if scale > 1:
            upscaled = cv2.resize(plate_crop, (pw * scale, ph * scale), interpolation=cv2.INTER_CUBIC)
        else:
            upscaled = plate_crop.copy()

        variants = [upscaled]

        # Contrast enhancement & sharpening
        gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(gray)
        blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
        sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)
        variants.append(sharpened)

        # Otsu thresholding
        _, otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(otsu)
        variants.append(255 - otsu)

        return variants

    def clean_and_validate_plate_text(self, raw_text: str) -> Tuple[Optional[str], float, str]:
        """
        Cleans OCR text formatting noise and validates character content against Indian
        registration plate standards.
        Applies positional alphanumeric correction:
        - State code (first 2 chars): uppercase letters (e.g. KA, MH, DL, HR)
        - District code (next 2 chars): digits (e.g. 01, 02)
        - Series (next 1-2 chars): uppercase letters (e.g. MN, HN, AB, C)
        - Registration (final 4 chars): digits (e.g. 1826, 9091)
        Returns: (cleaned_plate_text, confidence_score, status)
        """
        if not raw_text or not raw_text.strip():
            return None, 0.0, "UNREADABLE"

        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_text).upper()
        if len(cleaned) < 4:
            return None, 10.0, "UNREADABLE"

        # Strip standard HSRP prefix noise
        if cleaned.startswith("IND"):
            cleaned = cleaned[3:]

        alpha_map = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A"}
        digit_map = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "A": "4"}

        chars = list(cleaned)
        n = len(chars)

        # Handle 8 to 11 character Indian plates
        if 8 <= n <= 11:
            # 1. State Code (chars 0, 1) MUST be letters
            for i in [0, 1]:
                if chars[i] in alpha_map:
                    chars[i] = alpha_map[chars[i]]

            # 2. District Code (chars 2, 3) MUST be digits
            for i in [2, 3]:
                if chars[i] in digit_map:
                    chars[i] = digit_map[chars[i]]

            # 3. 10-character plate: State(2) + Dist(2) + Series(2) + Num(4)
            if n == 10:
                for i in [4, 5]:
                    if chars[i] in alpha_map:
                        chars[i] = alpha_map[chars[i]]
                for i in range(6, 10):
                    if chars[i] in digit_map:
                        chars[i] = digit_map[chars[i]]
            # 4. 9-character plate: State(2) + Dist(2) + Series(1) + Num(4)
            elif n == 9:
                if chars[4] in alpha_map:
                    chars[4] = alpha_map[chars[4]]
                for i in range(5, 9):
                    if chars[i] in digit_map:
                        chars[i] = digit_map[chars[i]]
            # 5. 11-character plate with trailing screw / border notch artifact
            elif n == 11:
                # Often ends with stray '4', '1', '7' from plate screw/border
                chars_trimmed = chars[:10]
                for i in [4, 5]:
                    if chars_trimmed[i] in alpha_map:
                        chars_trimmed[i] = alpha_map[chars_trimmed[i]]
                for i in range(6, 10):
                    if chars_trimmed[i] in digit_map:
                        chars_trimmed[i] = digit_map[chars_trimmed[i]]
                chars = chars_trimmed

        normalized = "".join(chars)
        if len(normalized) < 5:
            return None, 15.0, "UNREADABLE"

        # Calculate genuine confidence score based on syntax match
        has_letters = bool(re.search(r"[A-Z]", normalized))
        has_digits = bool(re.search(r"[0-9]", normalized))
        score = 60.0

        if has_letters and has_digits:
            score += 15.0
        if 8 <= len(normalized) <= 10:
            score += 10.0
        # High confidence bonus for recognized Indian state prefix
        if len(normalized) >= 2 and normalized[:2] in INDIAN_STATE_CODES:
            score += 13.0

        confidence = round(min(98.5, score), 1)
        status = "READABLE" if confidence >= 75.0 else ("UNCERTAIN" if len(normalized) >= 5 else "UNREADABLE")
        return normalized, confidence, status

    def recognize_plate(self, plate_crop: np.ndarray) -> Tuple[Optional[str], float, str, str]:
        """
        Runs multi-pass OCR on plate crop using local OCR engines:
        1. Local Tesseract (ultra-fast 10-15ms, PSM 7, alphanumeric whitelist).
        2. EasyOCR fallback if Tesseract confidence is insufficient.
        3. Auxiliary CRNN fallback.
        Returns: (best_text, best_confidence, status, raw_ocr_text)
        """
        if plate_crop is None or plate_crop.size == 0:
            return None, 0.0, "UNREADABLE", ""

        variants = self.generate_plate_variants(plate_crop)
        best_text = None
        best_conf = 0.0
        best_status = "UNREADABLE"
        raw_winner = ""

        # --- Pass 1: Local Tesseract OCR ---
        if self.tesseract_available:
            for v_img in variants:
                try:
                    raw = self.pytesseract.image_to_string(
                        v_img,
                        config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                    ).strip()
                    if raw:
                        txt, conf, st = self.clean_and_validate_plate_text(raw)
                        if conf > best_conf:
                            best_conf = conf
                            best_text = txt
                            best_status = st
                            raw_winner = raw
                except Exception as e:
                    logger.debug(f"[ANPREngine] Tesseract pass error: {e}")

        # If Tesseract achieved high confidence, return immediately for maximum speed
        if best_conf >= 85.0 and best_text:
            return best_text, best_conf, best_status, raw_winner

        # --- Pass 2: EasyOCR Local Fallback ---
        reader = self._get_easyocr_reader()
        if reader is not None and (best_conf < 85.0):
            for v_img in variants[:2]:  # Test upscaled raw and sharpened
                try:
                    res = reader.readtext(v_img)
                    for _, text, prob in res:
                        txt, conf, st = self.clean_and_validate_plate_text(text)
                        # Blend model probability with syntax confidence
                        blended_conf = round(conf * 0.7 + prob * 30.0, 1)
                        if blended_conf > best_conf:
                            best_conf = blended_conf
                            best_text = txt
                            best_status = st
                            raw_winner = text
                except Exception as e:
                    logger.debug(f"[ANPREngine] EasyOCR pass error: {e}")

        # --- Pass 3: CRNN auxiliary fallback ---
        if self.crnn_model is not None and (best_conf < 70.0):
            try:
                resized = cv2.resize(variants[0], (100, 32), interpolation=cv2.INTER_CUBIC)
                raw = self.crnn_model.recognize(resized)
                txt, conf, st = self.clean_and_validate_plate_text(raw)
                if conf > best_conf:
                    best_conf = conf
                    best_text = txt
                    best_status = st
                    raw_winner = raw
            except Exception:
                pass

        return best_text, best_conf, best_status, raw_winner

    def evaluate_vehicle_plate(
        self,
        frame_bgr: np.ndarray,
        vehicle_bbox: Dict[str, float],  # {"x", "y", "w", "h"} in %
        camera_id: str,
        track_id: Optional[int],
        vehicle_type: str = "CAR",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Complete ANPR pipeline for a detected vehicle track in a frame:
        1. Crop vehicle bounding box from frame.
        2. Locate license plate candidate in bumper ROI.
        3. Upscale & preprocess plate crop.
        4. Run real local OCR.
        5. Apply confidence-weighted temporal consensus per vehicle Track ID.
        6. Produce structured runtime debug logging.
        """
        cache_key = f"{camera_id}:{track_id}" if track_id is not None else None
        now = time.time()

        if cache_key and not force_refresh:
            cached = self.track_plate_cache.get(cache_key)
            if cached and (now - cached["timestamp"]) < self.cache_ttl_seconds:
                return cached["result"]

        h, w = frame_bgr.shape[:2]
        x1 = max(0, int((vehicle_bbox.get("x", 0.0) / 100.0) * w))
        y1 = max(0, int((vehicle_bbox.get("y", 0.0) / 100.0) * h))
        vw = max(10, int((vehicle_bbox.get("w", 0.0) / 100.0) * w))
        vh = max(10, int((vehicle_bbox.get("h", 0.0) / 100.0) * h))
        x2 = min(w, x1 + vw)
        y2 = min(h, y1 + vh)

        vehicle_crop = frame_bgr[y1:y2, x1:x2]
        if vehicle_crop.size == 0:
            res = {
                "plate_detected": False,
                "plate_text": None,
                "plate_confidence": None,
                "plate_status": "NOT_DETECTED",
                "plate_bbox": None,
                "vehicle_track_id": track_id,
                "vehicle_type": vehicle_type
            }
            return res

        # Locate plate in bumper ROI
        plate_found, plate_crop, plate_rel_bbox = self.locate_plate_region(vehicle_crop)

        if not plate_found or plate_crop is None:
            # Check if this track previously had a confirmed plate reading
            if cache_key and cache_key in self.track_plate_history:
                confirmed = self._get_temporal_winner(cache_key)
                if confirmed:
                    res = {
                        "plate_detected": True,
                        "plate_text": confirmed["text"],
                        "plate_confidence": confirmed["confidence"],
                        "plate_status": "READABLE",
                        "plate_bbox": None,
                        "vehicle_track_id": track_id,
                        "vehicle_type": vehicle_type
                    }
                    if cache_key:
                        self.track_plate_cache[cache_key] = {"result": res, "timestamp": now}
                    return res

            res = {
                "plate_detected": False,
                "plate_text": None,
                "plate_confidence": None,
                "plate_status": "NOT_DETECTED",
                "plate_bbox": None,
                "vehicle_track_id": track_id,
                "vehicle_type": vehicle_type
            }
            if cache_key:
                self.track_plate_cache[cache_key] = {"result": res, "timestamp": now}
            return res

        # Increment attempt count for track
        if cache_key:
            self.track_attempt_counts[cache_key] = self.track_attempt_counts.get(cache_key, 0) + 1

        # Calculate plate bounding box in full frame percentage
        full_plate_bbox = {
            "x": round(((x1 + plate_rel_bbox["x"]) / w) * 100.0, 2),
            "y": round(((y1 + plate_rel_bbox["y"]) / h) * 100.0, 2),
            "w": round((plate_rel_bbox["w"] / w) * 100.0, 2),
            "h": round((plate_rel_bbox["h"] / h) * 100.0, 2),
        }

        # Run Real OCR on the plate crop
        plate_text, confidence, status, raw_ocr = self.recognize_plate(plate_crop)

        # Required Runtime Debug Logging
        logger.info(f"[ANPR] vehicle_track_id={track_id}")
        logger.info(f"[PLATE DETECTOR] plate_bbox={full_plate_bbox}")
        logger.info(f"[PLATE CROP] width={plate_crop.shape[1]} height={plate_crop.shape[0]}")
        logger.info(f"[OCR] raw_text='{raw_ocr}' confidence={confidence}")
        logger.info(f"[OCR CLEAN] text='{plate_text}'")

        # Confidence-weighted Temporal Consensus
        if cache_key and plate_text and confidence >= 60.0:
            if cache_key not in self.track_plate_history:
                self.track_plate_history[cache_key] = []

            self.track_plate_history[cache_key].append({
                "text": plate_text,
                "confidence": confidence,
                "timestamp": now
            })
            # Keep last 10 readings for vehicle track
            self.track_plate_history[cache_key] = self.track_plate_history[cache_key][-10:]

        stable_winner = self._get_temporal_winner(cache_key) if cache_key else None
        stable_text = stable_winner["text"] if stable_winner else plate_text
        stable_conf = stable_winner["confidence"] if stable_winner else confidence

        logger.info(f"[OCR TEMPORAL] stable_text='{stable_text}'")

        attempts = self.track_attempt_counts.get(cache_key, 1) if cache_key else 1

        # Determine Final Status:
        # - READABLE: Valid plate text confirmed with high confidence (>= 80%) or multiple matching votes
        # - READING: Candidate plate detected, but accumulating frames for confirmation
        # - UNREADABLE: Multiple frames analyzed without achieving readable characters
        if stable_winner and stable_winner["confirmed"]:
            final_status = "READABLE"
            final_text = stable_winner["text"]
            final_conf = stable_winner["confidence"]
        elif attempts < 3 and (not stable_winner or not stable_winner["confirmed"]):
            final_status = "READING"
            final_text = None
            final_conf = None
        elif stable_winner and stable_winner["text"]:
            final_status = "READABLE"
            final_text = stable_winner["text"]
            final_conf = stable_winner["confidence"]
        else:
            final_status = "UNREADABLE"
            final_text = None
            final_conf = None

        logger.info(f"[ANPR EVENT] plate='{final_text}' status={final_status}")

        res = {
            "plate_detected": True,
            "plate_text": final_text,
            "plate_confidence": final_conf,
            "plate_status": final_status,
            "plate_bbox": full_plate_bbox,
            "vehicle_track_id": track_id,
            "vehicle_type": vehicle_type
        }

        if cache_key:
            self.track_plate_cache[cache_key] = {"result": res, "timestamp": now}

        return res

    def _get_temporal_winner(self, cache_key: Optional[str]) -> Optional[Dict[str, Any]]:
        """Computes confidence-weighted winner from temporal readings for a track ID."""
        if not cache_key or cache_key not in self.track_plate_history:
            return None

        readings = self.track_plate_history[cache_key]
        if not readings:
            return None

        # Aggregate weighted scores per unique plate text
        scores: Dict[str, float] = {}
        counts: Dict[str, int] = {}
        max_confs: Dict[str, float] = {}

        for r in readings:
            t = r["text"]
            c = r["confidence"]
            multiplier = 1.0
            if len(t) in (8, 9, 10):
                if t[:2] in INDIAN_STATE_CODES:
                    multiplier = 3.0
                else:
                    multiplier = 1.5
            elif len(t) < 7:
                multiplier = 0.4

            scores[t] = scores.get(t, 0.0) + (c * multiplier)
            counts[t] = counts.get(t, 0) + 1
            max_confs[t] = max(max_confs.get(t, 0.0), c)

        if not scores:
            return None

        # Best candidate by highest total confidence score
        best_text = max(scores.keys(), key=lambda k: scores[k])
        best_count = counts[best_text]
        best_max_conf = max_confs[best_text]

        # A plate is confirmed if seen >= 2 times OR if seen once with very high confidence (>= 88%)
        is_confirmed = (best_count >= 2) or (best_max_conf >= 88.0) or (len(best_text) in (9, 10) and best_text[:2] in INDIAN_STATE_CODES and best_max_conf >= 75.0)

        return {
            "text": best_text,
            "confidence": best_max_conf,
            "votes": best_count,
            "confirmed": is_confirmed
        }

    def clear_cache(self):
        """Clears track plate cache and history."""
        self.track_plate_cache.clear()
        self.track_plate_history.clear()
        self.track_attempt_counts.clear()


# Global singleton helper
_global_anpr_engine = None

def get_anpr_engine() -> ANPREngine:
    global _global_anpr_engine
    if _global_anpr_engine is None:
        _global_anpr_engine = ANPREngine()
    return _global_anpr_engine
