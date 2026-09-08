"""
IBVAP Detection Module — YOLOv8n Integration
=============================================
Runs real YOLOv8 inference on video frames and extracts normalized detections.
"""
import os
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger("detector")

# COCO Class ID mappings to IBVAP standardized types
COCO_PERSON_IDS = {0}
COCO_VEHICLE_IDS = {1: "BICYCLE", 2: "CAR", 3: "MOTORCYCLE", 5: "BUS", 7: "TRUCK"}
COCO_ANIMAL_IDS = {
    14: "BIRD", 15: "CAT", 16: "DOG", 17: "HORSE", 
    18: "SHEEP", 19: "COW", 20: "ELEPHANT", 21: "BEAR", 
    22: "ZEBRA", 23: "GIRAFFE"
}

ALL_SUPPORTED_CLASSES = set(COCO_PERSON_IDS) | set(COCO_VEHICLE_IDS.keys()) | set(COCO_ANIMAL_IDS.keys())


class Detection:
    """Represents a single object detection normalized for IBVAP."""
    def __init__(
        self,
        object_type: str,
        object_id: str,
        confidence: float,
        bbox: dict,
        event_type: str = "PERSON_DETECTED",
        camera_id: str = "BOP-07",
        track_id: Optional[int] = None,
        raw_xyxy: Optional[List[float]] = None
    ):
        self.object_type = object_type     # PERSON, VEHICLE, ANIMAL
        self.object_id   = object_id       # e.g. "Person #1" or "Vehicle #3"
        self.confidence  = confidence      # 0.0 - 100.0
        self.bbox        = bbox            # {"x": %, "y": %, "w": %, "h": %} (0-100)
        self.event_type  = event_type      # PERSON_DETECTED, VEHICLE_DETECTED, etc.
        self.camera_id   = camera_id
        self.track_id    = track_id        # integer track ID
        self.raw_xyxy    = raw_xyxy or []  # pixel coordinates [x1, y1, x2, y2]

    def to_dict(self) -> dict:
        return {
            "object_type": self.object_type,
            "object_id": self.object_id,
            "confidence": round(self.confidence, 1),
            "bbox": self.bbox,
            "event_type": self.event_type,
            "camera_id": self.camera_id,
        }


class Detector:
    """
    YOLOv8 Object Detector for IBVAP Surveillance.
    Loads yolov8n.pt and executes frame inference with ByteTrack integration.
    """

    def __init__(self, model_path: Optional[str] = None, conf_threshold: float = 0.45):
        # Dynamically discover model file across workspace and runtime environments
        self.model_path = self._resolve_model_path(model_path)
        self.conf_threshold = conf_threshold
        self.model = None
        self.load_model()

    @staticmethod
    def _resolve_model_path(candidate_path: Optional[str]) -> str:
        if candidate_path and os.path.exists(candidate_path):
            return candidate_path

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = [
            os.path.normpath(os.path.join(base_dir, "models", "yolov8n.pt")),
            os.path.normpath(os.path.join(base_dir, "..", "models", "yolov8n.pt")),
            os.path.normpath(os.path.join(os.getcwd(), "models", "yolov8n.pt")),
            os.path.normpath(os.path.join(os.getcwd(), "yolov8n.pt")),
            os.path.normpath(r"C:\Users\thaku\OneDrive\Desktop\IBVAP\models\yolov8n.pt"),
            os.path.normpath(r"C:\Users\thaku\OneDrive\Desktop\IBVAP\yolov8n.pt"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c

        return candidate_path or candidates[0]

    def load_model(self):
        """Load pretrained Ultralytics YOLO model."""
        try:
            from ultralytics import YOLO
            if os.path.exists(self.model_path):
                logger.info(f"[Detector] Loading YOLO model from {self.model_path}...")
                self.model = YOLO(self.model_path)
            else:
                logger.warning(f"[Detector] Model file not found at {self.model_path}. Loading yolov8n directly...")
                self.model = YOLO("yolov8n.pt")
            logger.info("[Detector] YOLOv8n model loaded successfully.")
        except Exception as e:
            logger.error(f"[Detector] Failed to load YOLO model: {e}")
            raise e

    def detect(self, frame, camera_id: str = "BOP-07", track: bool = True) -> List[Detection]:
        """
        Run detection and tracking on a single BGR OpenCV frame.
        
        Args:
            frame: OpenCV numpy image (H, W, 3)
            camera_id: Camera identifier (e.g. "BOP-07")
            track: Whether to enable persistent tracking across frames

        Returns:
            List of normalized Detection objects
        """
        if self.model is None or frame is None:
            return []

        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return []

        detections: List[Detection] = []

        try:
            if track:
                results = self.model.track(
                    source=frame,
                    persist=True,
                    tracker="bytetrack.yaml",    # Explicit ByteTrack (better occlusion handling)
                    conf=self.conf_threshold,
                    iou=0.5,                      # IoU threshold for track association
                    classes=list(ALL_SUPPORTED_CLASSES),
                    verbose=False,
                    imgsz=320
                )
            else:
                results = self.model.predict(
                    source=frame,
                    conf=self.conf_threshold,
                    classes=list(ALL_SUPPORTED_CLASSES),
                    verbose=False,
                    imgsz=320
                )

            if not results or len(results) == 0:
                return []

            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                return []

            for i, box in enumerate(boxes):
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item()) * 100.0  # convert 0.0-1.0 to 0-100%

                # Parse Track ID
                track_id = None
                if box.id is not None:
                    track_id = int(box.id[0].item())

                # Map Class to Standard Object Type
                if cls_id in COCO_PERSON_IDS:
                    object_type = "PERSON"
                    object_label = f"Person #{track_id if track_id is not None else i+1}"
                    event_type = "PERSON_DETECTED"
                elif cls_id in COCO_VEHICLE_IDS:
                    object_type = "VEHICLE"
                    vtype = COCO_VEHICLE_IDS[cls_id].title()
                    object_label = f"{vtype} #{track_id if track_id is not None else i+1}"
                    event_type = "VEHICLE_DETECTED"
                elif cls_id in COCO_ANIMAL_IDS:
                    object_type = "ANIMAL"
                    atype = COCO_ANIMAL_IDS[cls_id].title()
                    object_label = f"{atype} #{track_id if track_id is not None else i+1}"
                    event_type = "PERSON_DETECTED" # mapped event
                else:
                    continue

                # Pixel coordinates [x1, y1, x2, y2]
                xyxy = box.xyxy[0].tolist()
                x1, y1, x2, y2 = xyxy

                # Convert to IBVAP 0-100% normalized coordinates
                norm_x = max(0.0, min(100.0, (x1 / w) * 100.0))
                norm_y = max(0.0, min(100.0, (y1 / h) * 100.0))
                norm_w = max(0.0, min(100.0, ((x2 - x1) / w) * 100.0))
                norm_h = max(0.0, min(100.0, ((y2 - y1) / h) * 100.0))

                bbox = {
                    "x": round(norm_x, 2),
                    "y": round(norm_y, 2),
                    "w": round(norm_w, 2),
                    "h": round(norm_h, 2)
                }

                det = Detection(
                    object_type=object_type,
                    object_id=object_label,
                    confidence=round(conf, 1),
                    bbox=bbox,
                    event_type=event_type,
                    camera_id=camera_id,
                    track_id=track_id,
                    raw_xyxy=[x1, y1, x2, y2]
                )
                detections.append(det)

        except Exception as e:
            logger.error(f"[Detector] Inference error: {e}")

        return detections
