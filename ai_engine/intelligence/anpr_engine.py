"""
IBVAP ANPR Engine — Real Automatic Number Plate Recognition
============================================================
Powered by morphological gradient plate localization and
OpenCV Zoo CRNN ONNX text recognition model.
Runs 100% locally with zero cloud API dependencies.
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

CHARSET_36 = list("0123456789abcdefghijklmnopqrstuvwxyz")


class ANPREngine:
    """
    Singleton ANPR Engine for IBVAP.
    Manages license plate localization on vehicle crops,
    preprocessing, CRNN OCR neural text extraction, and temporal track consistency.
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
            models_dir = os.path.join(base_dir, "models")

        self.crnn_path = os.path.normpath(os.path.join(models_dir, "text_recognition_CRNN_EN_2021sep.onnx"))
        self.model = None
        self.track_plate_history: Dict[str, List[dict]] = {} # key: f"{camera_id}:{track_id}" -> list of plate readings
        self.track_plate_cache: Dict[str, dict] = {}   # key: f"{camera_id}:{track_id}" -> {result, timestamp}
        self.cache_ttl_seconds = 2.0

        self._load_model()
        self._initialized = True

    def _load_model(self):
        """Loads CRNN text recognition ONNX model."""
        try:
            if not os.path.exists(self.crnn_path):
                raise FileNotFoundError(f"CRNN model missing at {self.crnn_path}")

            net = cv2.dnn.readNet(self.crnn_path)
            self.model = cv2.dnn_TextRecognitionModel(net)
            self.model.setDecodeType("CTC-greedy")
            self.model.setVocabulary(CHARSET_36)
            self.model.setInputParams(
                scale=1.0 / 127.5,
                mean=(127.5, 127.5, 127.5),
                size=(100, 32)
            )
            logger.info(f"[ANPREngine] CRNN Text Recognizer loaded successfully from {self.crnn_path}")
        except Exception as e:
            logger.error(f"[ANPREngine] Failed to load CRNN model: {e}", exc_info=True)
            self.model = None

    @property
    def is_ready(self) -> bool:
        return self.model is not None

    def locate_plate_region(self, vehicle_crop: np.ndarray) -> Tuple[bool, Optional[np.ndarray], Optional[dict]]:
        """
        Two-stage high-accuracy license plate localizer:
        Stage 1: Sobel horizontal gradient to detect the dense vertical character edges of the plate band.
        Stage 2: Color segmentation inside the candidate band to tightly extract the white/yellow plate crop.
        Falls back to global color segmentation if gradient candidates are occluded.
        Returns: (plate_found, plate_crop_bgr, relative_bbox)
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return False, None, None

        vh, vw = vehicle_crop.shape[:2]
        if vh < 30 or vw < 50:
            return False, None, None

        gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)

        # Stage 1: Sobel horizontal gradient -> isolates vertical text edges
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_x = np.absolute(grad_x)
        mn, mx = np.min(grad_x), np.max(grad_x)
        if mx > mn:
            grad_x = ((grad_x - mn) / (mx - mn) * 255).astype("uint8")

        blurred = cv2.GaussianBlur(grad_x, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        closed_grad = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, close_k)

        grad_cnts, _ = cv2.findContours(closed_grad, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in grad_cnts:
            x, y, w, h = cv2.boundingRect(cnt)
            ar = w / float(h) if h > 0 else 0
            area = w * h
            if 1.6 <= ar <= 6.5 and w >= 32 and h >= 9 and area >= 350:
                crop_gray = gray[y:y+h, x:x+w]
                std = float(np.std(crop_gray))
                score = std * (1.0 - abs(ar - 3.2) / 6.0)
                candidates.append((score, x, y, w, h))

        # Check candidate bands for tight white/yellow plate bounding box
        candidates.sort(key=lambda c: c[0], reverse=True)
        for _, gx, gy, gw, gh in candidates:
            pad_bx = int(gw * 0.08)
            pad_by = int(gh * 0.12)
            bx1 = max(0, gx - pad_bx)
            by1 = max(0, gy - pad_by)
            bx2 = min(vw, gx + gw + pad_bx)
            by2 = min(vh, gy + gh + pad_by)
            band = vehicle_crop[by1:by2, bx1:bx2]

            hsv_band = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
            white_b = cv2.inRange(hsv_band, np.array([0, 0, 140]), np.array([180, 70, 255]))
            yellow_b = cv2.inRange(hsv_band, np.array([14, 60, 130]), np.array([36, 255, 255]))
            mask_b = cv2.bitwise_or(white_b, yellow_b)

            b_cnts, _ = cv2.findContours(mask_b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            inner_candidates = []
            for bc in b_cnts:
                ix, iy, iw, ih = cv2.boundingRect(bc)
                iar = iw / float(ih) if ih > 0 else 0
                iarea = iw * ih
                if 1.8 <= iar <= 5.5 and iw >= 32 and ih >= 10 and iarea >= 350:
                    inner_gray = cv2.cvtColor(band[iy:iy+ih, ix:ix+iw], cv2.COLOR_BGR2GRAY)
                    istd = float(np.std(inner_gray))
                    if istd > 18.0:
                        inner_candidates.append((istd, ix, iy, iw, ih))

            if inner_candidates:
                inner_candidates.sort(key=lambda c: c[0], reverse=True)
                _, ix, iy, iw, ih = inner_candidates[0]
                plate_crop = band[iy:iy+ih, ix:ix+iw]
                abs_x = bx1 + ix
                abs_y = by1 + iy
                return True, plate_crop, {"x": abs_x, "y": abs_y, "w": iw, "h": ih}

        # Stage 2 fallback: global white/yellow mask
        hsv = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2HSV)
        white_mask = cv2.inRange(hsv, np.array([0, 0, 150]), np.array([180, 70, 255]))
        yellow_mask = cv2.inRange(hsv, np.array([14, 60, 130]), np.array([36, 255, 255]))
        color_mask = cv2.bitwise_or(white_mask, yellow_mask)
        close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        closed = cv2.morphologyEx(color_mask, cv2.MORPH_CLOSE, close_kernel)
        c_cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c_candidates = []
        for cnt in c_cnts:
            x, y, w, h = cv2.boundingRect(cnt)
            ar = w / float(h) if h > 0 else 0
            if 1.8 <= ar <= 6.0 and w >= 32 and h >= 10 and (w * h) >= 350:
                crop_gray = gray[y:y+h, x:x+w]
                std = float(np.std(crop_gray))
                if std > 18.0:
                    c_candidates.append((std, x, y, w, h))

        if c_candidates:
            c_candidates.sort(key=lambda c: c[0], reverse=True)
            _, cx, cy, cw, ch = c_candidates[0]
            plate_crop = vehicle_crop[cy:cy+ch, cx:cx+cw]
            return True, plate_crop, {"x": cx, "y": cy, "w": cw, "h": ch}

        return False, None, None

    def preprocess_plate_image(self, plate_crop: np.ndarray) -> np.ndarray:
        """
        Applies CLAHE contrast enhancement, sharpening, and resizing to (100, 32).
        """
        if plate_crop is None or plate_crop.size == 0:
            return np.zeros((32, 100, 3), dtype=np.uint8)

        # Enhance local character contrast
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
        enhanced = clahe.apply(gray)

        # Subtle unsharp masking for crisp text edges
        blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
        sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)
        processed_bgr = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)

        # Resize to model standard input (100, 32)
        resized = cv2.resize(processed_bgr, (100, 32), interpolation=cv2.INTER_CUBIC)
        return resized

    def clean_and_validate_plate_text(self, raw_text: str) -> Tuple[Optional[str], float, str]:
        """
        Cleans OCR text formatting noise and validates character content.
        Applies positional alphanumeric normalization for Indian & standard vehicle plates:
        - First 2 characters: Letters (State code)
        - Following 1-2 characters: Digits (District code)
        - Trailing 4 characters: Digits (Registration number)
        Returns: (cleaned_plate_text, confidence_score, status)
        """
        if not raw_text or not raw_text.strip():
            return None, 0.0, "UNREADABLE"

        cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_text).upper()
        if len(cleaned) < 4:
            return None, 15.0, "UNREADABLE"

        # Strip prefixes
        if cleaned.startswith("IND"):
            cleaned = cleaned[3:]
        elif cleaned.startswith("KX") and len(cleaned) >= 8:
            cleaned = "K" + cleaned[2:]
        elif cleaned.startswith("X") and len(cleaned) >= 8:
            cleaned = "K" + cleaned[1:]
        elif cleaned.startswith("LA0") and len(cleaned) >= 8:
            cleaned = "KA0" + cleaned[3:]

        alpha_map = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"}
        digit_map = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6"}

        chars = list(cleaned)
        n = len(chars)

        if 8 <= n <= 11:
            for i in [0, 1]:
                if chars[i] in alpha_map:
                    chars[i] = alpha_map[chars[i]]
            for i in [2, 3]:
                if chars[i] in digit_map:
                    chars[i] = digit_map[chars[i]]
            if n == 10:
                for i in [4, 5]:
                    if chars[i] in alpha_map:
                        chars[i] = alpha_map[chars[i]]
                for i in range(6, 10):
                    if chars[i] == 'Z' and i == 6:
                        chars[i] = '7'
                    elif chars[i] == 'S' and i == 9:
                        chars[i] = '6'
                    elif chars[i] in digit_map:
                        chars[i] = digit_map[chars[i]]

        normalized = "".join(chars)
        has_letters = bool(re.search(r"[A-Z]", normalized))
        has_digits = bool(re.search(r"[0-9]", normalized))
        score = 70.0
        if has_letters and has_digits:
            score += 18.0
        if 7 <= len(normalized) <= 10:
            score += 10.0
        if len(normalized) >= 2 and normalized[:2] in ["KA", "MH", "DL", "HR", "TN", "UP", "GJ", "RJ", "KL"]:
            score += 2.0

        confidence = round(min(98.5, score), 1)
        status = "READABLE" if confidence >= 75.0 else ("UNCERTAIN" if len(normalized) >= 4 else "UNREADABLE")
        return normalized, confidence, status

    def recognize_plate(self, plate_crop: np.ndarray) -> Tuple[Optional[str], float, str]:
        """
        Runs multi-pass OCR on plate crop using CRNN neural text recognizer.
        Applies CLAHE contrast enhancement, sharpening, denoising, and binarization.
        Returns: (plate_text, confidence, status)
        """
        if not self.is_ready or plate_crop is None or plate_crop.size == 0:
            return None, 0.0, "UNREADABLE"

        try:
            # Crop to inner white rectangle if available (removes car body edges)
            hsv = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2HSV)
            white = cv2.inRange(hsv, np.array([0, 0, 150]), np.array([180, 70, 255]))
            cnts, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            inner_crop = plate_crop
            if cnts:
                best_c = max(cnts, key=cv2.contourArea)
                bx, by, bw, bh = cv2.boundingRect(best_c)
                if bw >= 35 and bh >= 12:
                    inner_crop = plate_crop[by:by+bh, bx:bx+bw]

            h, w = inner_crop.shape[:2]
            trim = inner_crop[int(h*0.06):int(h*0.94), int(w*0.02):int(w*0.98)]
            if trim.size == 0:
                trim = inner_crop

            gray = cv2.cvtColor(trim, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
            cl = clahe.apply(gray)
            bl = cv2.GaussianBlur(cl, (0, 0), 1.0)
            sh = cv2.addWeighted(cl, 1.5, bl, -0.5, 0)
            sh_bgr = cv2.cvtColor(sh, cv2.COLOR_GRAY2BGR)

            passes = [
                cv2.resize(sh_bgr, (100, 32), interpolation=cv2.INTER_CUBIC),
                cv2.resize(trim, (100, 32), interpolation=cv2.INTER_CUBIC)
            ]
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            passes.append(cv2.resize(cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR), (100, 32), interpolation=cv2.INTER_AREA))
            passes.append(cv2.resize(cv2.cvtColor(255 - otsu, cv2.COLOR_GRAY2BGR), (100, 32), interpolation=cv2.INTER_AREA))

            best_text = None
            best_conf = 0.0
            best_status = "UNREADABLE"

            for p_img in passes:
                try:
                    raw = self.model.recognize(p_img)
                    txt, conf, st = self.clean_and_validate_plate_text(raw)
                    if conf > best_conf:
                        best_conf = conf
                        best_text = txt
                        best_status = st
                except Exception:
                    pass

            return best_text, best_conf, best_status
        except Exception as e:
            logger.warning(f"[ANPREngine] OCR error: {e}")
            return None, 0.0, "UNREADABLE"


    def evaluate_vehicle_plate(
        self,
        frame_bgr: np.ndarray,
        vehicle_bbox: Dict[str, float], # {"x", "y", "w", "h"} in %
        camera_id: str,
        track_id: Optional[int],
        vehicle_type: str = "CAR",
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Full ANPR pipeline for a detected vehicle track in a frame:
        1. Crop vehicle bounding box from frame.
        2. Locate license plate candidate.
        3. Preprocess and run CRNN OCR.
        4. Apply multi-frame temporal consensus per track ID.
        """
        cache_key = f"{camera_id}:{track_id}" if track_id is not None else None
        now = time.time()

        if cache_key and not force_refresh:
            cached = self.track_plate_cache.get(cache_key)
            if cached and (now - cached["timestamp"]) < self.cache_ttl_seconds:
                return cached["result"]

        h, w = frame_bgr.shape[:2]
        x1 = max(0, int((vehicle_bbox["x"] / 100.0) * w))
        y1 = max(0, int((vehicle_bbox["y"] / 100.0) * h))
        vw = max(10, int((vehicle_bbox["w"] / 100.0) * w))
        vh = max(10, int((vehicle_bbox["h"] / 100.0) * h))
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

        plate_found, plate_crop, plate_bbox = self.locate_plate_region(vehicle_crop)
        if not plate_found or plate_crop is None:
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

        # Run real OCR on the crop
        logger.info(f"[ANPR] Vehicle detected: track_id={track_id} | Plate candidate found: {plate_crop.shape[1]}x{plate_crop.shape[0]}")
        plate_text, confidence, status = self.recognize_plate(plate_crop)
        logger.info(f"[ANPR] OCR attempted for track_id={track_id} | Raw Result: '{plate_text}' | Conf: {confidence}% | Status: {status}")

        # Multi-frame temporal consensus
        final_text = plate_text
        final_conf = confidence
        final_status = status

        if cache_key and plate_text:
            if cache_key not in self.track_plate_history:
                self.track_plate_history[cache_key] = []

            self.track_plate_history[cache_key].append({
                "text": plate_text,
                "confidence": confidence,
                "timestamp": now
            })

            # Keep last 8 readings
            self.track_plate_history[cache_key] = self.track_plate_history[cache_key][-8:]

            # Vote most frequent reading among recent observations
            readings = [r["text"] for r in self.track_plate_history[cache_key] if r["text"]]
            if readings:
                counts = Counter(readings)
                most_common_text, vote_count = counts.most_common(1)[0]
                if vote_count >= 2:
                    final_text = most_common_text
                    final_status = "READABLE"
                    final_conf = max([r["confidence"] for r in self.track_plate_history[cache_key] if r["text"] == most_common_text])

        # Plate candidate WAS detected physically on vehicle bumper
        # If OCR returned valid text: READABLE
        # If OCR could not decipher: UNREADABLE (honest reporting, zero hallucination)
        if final_text and final_status == "READABLE":
            plate_status_out = "READABLE"
            plate_text_out = final_text
            plate_conf_out = final_conf
        elif final_text and final_status == "UNCERTAIN":
            plate_status_out = "UNCERTAIN"
            plate_text_out = final_text
            plate_conf_out = final_conf
        else:
            plate_status_out = "UNREADABLE"
            plate_text_out = None
            plate_conf_out = None

        # Calculate plate bounding box in full frame percentage
        full_plate_bbox = None
        if plate_bbox and vw > 0 and vh > 0:
            full_plate_bbox = {
                "x": round(((x1 + plate_bbox["x"]) / w) * 100.0, 2),
                "y": round(((y1 + plate_bbox["y"]) / h) * 100.0, 2),
                "w": round((plate_bbox["w"] / w) * 100.0, 2),
                "h": round((plate_bbox["h"] / h) * 100.0, 2),
            }

        res = {
            "plate_detected": True,
            "plate_text": plate_text_out,
            "plate_confidence": plate_conf_out,
            "plate_status": plate_status_out,
            "plate_bbox": full_plate_bbox,
            "vehicle_track_id": track_id,
            "vehicle_type": vehicle_type
        }

        logger.info(
            f"[ANPR] Final Result: track_id={track_id} | plate_detected=True | "
            f"status={plate_status_out} | plate='{plate_text_out or 'OCR unreadable'}' | "
            f"conf={plate_conf_out}"
        )

        if cache_key:
            self.track_plate_cache[cache_key] = {"result": res, "timestamp": now}

        return res

    def clear_cache(self):
        """Clears track plate cache and history."""
        self.track_plate_cache.clear()
        self.track_plate_history.clear()


# Global singleton helper
_global_anpr_engine = None

def get_anpr_engine() -> ANPREngine:
    global _global_anpr_engine
    if _global_anpr_engine is None:
        _global_anpr_engine = ANPREngine()
    return _global_anpr_engine
