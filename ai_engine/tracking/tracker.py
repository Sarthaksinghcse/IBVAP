"""
IBVAP Object Tracker Module
===========================
Maintains persistent tracks, track lifetimes, trajectories, and dwell times.
Includes centroid / IoU distance matching fallback for stable persistent IDs.
"""
import time
import math
import logging
from typing import List, Dict, Optional
from ai_engine.detection.detector import Detection

logger = logging.getLogger("tracker")


VEHICLE_CLASSES = {"CAR", "TRUCK", "BUS", "MOTORCYCLE", "BICYCLE", "VEHICLE"}


def are_classes_compatible(cls1: str, cls2: str) -> bool:
    """Allow association across flickering vehicle subclasses (e.g. Car vs Truck)."""
    if cls1 == cls2:
        return True
    if cls1 in VEHICLE_CLASSES and cls2 in VEHICLE_CLASSES:
        return True
    return False


class TrackedObject:
    """Represents an active track across multiple frames."""
    def __init__(self, track_id: int, object_type: str, object_label: str, bbox: dict, confidence: float):
        self.track_id      = track_id          # Integer track ID
        self.object_type   = object_type       # PERSON, VEHICLE, ANIMAL
        self.object_label  = object_label      # e.g. "Person #1"
        self.bbox          = bbox              # {"x", "y", "w", "h"} in %
        self.confidence    = confidence
        self.first_seen    = time.time()
        self.last_seen     = time.time()
        self.frame_count   = 1
        self.in_zone       = False
        self.was_in_zone   = False
        self.just_entered_zone = False
        self.just_exited_zone  = False
        self.zone_name     = None
        self.zone_entry_time: Optional[float] = None
        self.trajectory    = []                # List of (center_x, center_y) points
        self.vx            = 0.0               # Estimated horizontal velocity (% per frame)
        self.vy            = 0.0               # Estimated vertical velocity (% per frame)

    @property
    def dwell_time(self) -> float:
        """Total time object has been tracked (seconds)."""
        return time.time() - self.first_seen

    @property
    def zone_dwell_time(self) -> float:
        """Time spent inside restricted zone (seconds)."""
        if self.in_zone and self.zone_entry_time is not None:
            return time.time() - self.zone_entry_time
        return 0.0

    @property
    def bottom_center(self) -> tuple:
        """(x%, y%) bottom-center reference point for zone testing."""
        bx = self.bbox["x"] + (self.bbox["w"] / 2.0)
        by = self.bbox["y"] + self.bbox["h"]
        return (bx, by)

    @property
    def center(self) -> tuple:
        """(center_x%, center_y%) centroid coordinate."""
        cx = self.bbox["x"] + (self.bbox["w"] / 2.0)
        cy = self.bbox["y"] + (self.bbox["h"] / 2.0)
        return (cx, cy)

    def update_zone_status(self, in_zone: bool, zone_name: Optional[str] = None):
        """Update spatial zone status, detect transitions, and manage zone dwell timers."""
        now = time.time()
        self.was_in_zone = self.in_zone
        self.just_entered_zone = (in_zone and not self.was_in_zone)
        self.just_exited_zone = (not in_zone and self.was_in_zone)

        if in_zone:
            if not self.in_zone:
                self.in_zone = True
                self.zone_entry_time = now
            if zone_name:
                self.zone_name = zone_name
        else:
            self.in_zone = False
            self.zone_name = None
            self.zone_entry_time = None


def _compute_iou(boxA: dict, boxB: dict) -> float:
    """Compute Intersection over Union between two bounding boxes in % coordinates."""
    xA = max(boxA["x"], boxB["x"])
    yA = max(boxA["y"], boxB["y"])
    xB = min(boxA["x"] + boxA["w"], boxB["x"] + boxB["w"])
    yB = min(boxA["y"] + boxA["h"], boxB["y"] + boxB["h"])

    interW = max(0.0, xB - xA)
    interH = max(0.0, yB - yA)
    interArea = interW * interH

    boxAArea = boxA["w"] * boxA["h"]
    boxBArea = boxB["w"] * boxB["h"]
    unionArea = boxAArea + boxBArea - interArea

    if unionArea <= 0.0:
        return 0.0
    return interArea / unionArea


class Tracker:
    """
    Robust Multi-Object Tracker and State Manager.
    Uses IoU overlap, centroid proximity, and ID remapping to maintain stable track IDs
    across pose changes, movements, head turns, and brief occlusions.
    """

    def __init__(self, max_missed_seconds: float = 6.0, match_distance_threshold: float = 35.0):
        self.tracks: Dict[int, TrackedObject] = {}
        self.yolo_to_stable_id: Dict[int, int] = {}
        self.max_missed_seconds = max_missed_seconds
        self.match_distance_threshold = match_distance_threshold
        self.next_fallback_id = 1
        logger.info("[Tracker] Object Tracker initialized.")

    def _find_best_matching_track(self, det: Detection, active_ids: set) -> Optional[int]:
        """Find the best existing unassigned track of the same type via unified IoU and distance scoring."""
        dx = det.bbox["x"] + det.bbox["w"] / 2.0
        dy = det.bbox["y"] + det.bbox["h"] / 2.0
        best_id = None
        best_score = -1.0

        for tid, trk in self.tracks.items():
            if tid in active_ids or not are_classes_compatible(trk.object_type, det.object_type):
                continue

            iou = _compute_iou(det.bbox, trk.bbox)
            # Predict position using estimated velocity for moving targets
            pred_cx = trk.center[0] + trk.vx
            pred_cy = trk.center[1] + trk.vy
            dist = math.hypot(dx - pred_cx, dy - pred_cy)

            # Combined score: IoU overlap takes priority [1.15, 2.0], proximity [0.0, 1.0)
            prox_score = max(0.0, 1.0 - (dist / self.match_distance_threshold))
            if iou >= 0.15:
                score = 1.0 + iou
            elif dist < self.match_distance_threshold:
                score = prox_score
            else:
                score = -1.0

            if score > best_score and score > 0.15:
                best_score = score
                best_id = tid

        return best_id

    def update(self, detections: List[Detection]) -> List[TrackedObject]:
        """
        Update active tracks with new frame detections.
        
        Args:
            detections: List of Detection objects from Detector

        Returns:
            List of currently active TrackedObject instances
        """
        current_time = time.time()
        active_ids = set()

        for det in detections:
            raw_tid = det.track_id
            tid = None

            # 1. Check if YOLO raw_tid has an existing stable mapping
            if raw_tid is not None and raw_tid in self.yolo_to_stable_id:
                mapped_id = self.yolo_to_stable_id[raw_tid]
                if mapped_id in self.tracks and mapped_id not in active_ids:
                    tid = mapped_id

            # 2. If no valid existing mapping, try spatial & IoU association with unassigned tracks
            if tid is None:
                matched_id = self._find_best_matching_track(det, active_ids)
                if matched_id is not None:
                    tid = matched_id
                    if raw_tid is not None:
                        self.yolo_to_stable_id[raw_tid] = tid
                else:
                    # 3. If YOLO gave a new raw_tid not matching any existing track
                    if raw_tid is not None:
                        tid = raw_tid
                        self.yolo_to_stable_id[raw_tid] = tid
                    else:
                        tid = self.next_fallback_id
                        self.next_fallback_id += 1

            det.track_id = tid

            # Preserve COCO class prefix
            if '#' in det.object_id:
                class_prefix = det.object_id.rsplit('#', 1)[0].strip()
            else:
                class_prefix = det.object_type.title()
            det.object_id = f"{class_prefix} #{tid}"
            active_ids.add(tid)

            if tid in self.tracks:
                # Update existing track with velocity smoothing
                track = self.tracks[tid]
                old_cx, old_cy = track.center
                new_cx = det.bbox["x"] + det.bbox["w"] / 2.0
                new_cy = det.bbox["y"] + det.bbox["h"] / 2.0
                inst_vx = new_cx - old_cx
                inst_vy = new_cy - old_cy
                track.vx = 0.6 * track.vx + 0.4 * inst_vx
                track.vy = 0.6 * track.vy + 0.4 * inst_vy

                # Adopt higher-confidence vehicle sub-type if flickering
                if are_classes_compatible(track.object_type, det.object_type) and det.confidence > track.confidence:
                    track.object_type = det.object_type
                    track.object_label = det.object_id

                track.bbox = det.bbox
                track.confidence = det.confidence
                track.last_seen = current_time
                track.frame_count += 1
                track.trajectory.append(track.bottom_center)
                if len(track.trajectory) > 50:
                    track.trajectory.pop(0)
            else:
                # Create new track
                track = TrackedObject(
                    track_id=tid,
                    object_type=det.object_type,
                    object_label=det.object_id,
                    bbox=det.bbox,
                    confidence=det.confidence
                )
                track.trajectory.append(track.bottom_center)
                self.tracks[tid] = track

        # Remove stale tracks past timeout
        stale_threshold = current_time - self.max_missed_seconds
        stale_ids = [tid for tid, trk in self.tracks.items() if trk.last_seen < stale_threshold]
        for tid in stale_ids:
            del self.tracks[tid]
            # Clean reverse mapping
            keys_to_del = [k for k, v in self.yolo_to_stable_id.items() if v == tid]
            for k in keys_to_del:
                del self.yolo_to_stable_id[k]

        active_objects = [self.tracks[tid] for tid in active_ids if tid in self.tracks]
        logger.info(f"[TRACKER] {len(active_objects)} active tracks")
        return active_objects

