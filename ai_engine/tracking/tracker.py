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
        self.zone_name     = None
        self.zone_entry_time: Optional[float] = None
        self.trajectory    = []                # List of (center_x, center_y) points

    @property
    def dwell_time(self) -> float:
        """Total time object has been tracked (seconds). Uses wall clock."""
        return time.time() - self.first_seen

    def get_dwell_time(self, current_time: float = None) -> float:
        """Total time object has been tracked. Accepts explicit timestamp for offline video."""
        if current_time is None:
            current_time = time.time()
        return current_time - self.first_seen

    @property
    def zone_dwell_time(self) -> float:
        """Time spent inside restricted zone (seconds). Uses wall clock."""
        if self.in_zone and self.zone_entry_time is not None:
            return time.time() - self.zone_entry_time
        return 0.0

    def get_zone_dwell_time(self, current_time: float = None) -> float:
        """Time spent inside restricted zone. Accepts explicit timestamp for offline video."""
        if current_time is None:
            current_time = time.time()
        if self.in_zone and self.zone_entry_time is not None:
            return current_time - self.zone_entry_time
        return 0.0

    def update_zone_status(self, in_zone: bool, zone_name: Optional[str] = None):
        """Update whether this object is inside a restricted zone and track entry time."""
        if in_zone and not self.in_zone:
            if self.zone_entry_time is None:
                self.zone_entry_time = time.time()
        elif not in_zone:
            self.zone_entry_time = None
        self.in_zone = in_zone
        if zone_name is not None:
            self.zone_name = zone_name

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

    def __init__(self, max_missed_seconds: float = 4.5, match_distance_threshold: float = 32.0):
        self.tracks: Dict[int, TrackedObject] = {}
        self.yolo_to_stable_id: Dict[int, int] = {}
        self.max_missed_seconds = max_missed_seconds
        self.match_distance_threshold = match_distance_threshold
        self.next_fallback_id = 1
        logger.info("[Tracker] Object Tracker initialized.")

    def _find_best_matching_track(self, det: Detection, active_ids: set) -> Optional[int]:
        """Find the best existing unassigned track of the same type via IoU and distance."""
        dx = det.bbox["x"] + det.bbox["w"] / 2.0
        dy = det.bbox["y"] + det.bbox["h"] / 2.0
        best_id = None
        best_score = -1.0

        for tid, trk in self.tracks.items():
            if tid in active_ids or trk.object_type != det.object_type:
                continue

            iou = _compute_iou(det.bbox, trk.bbox)
            tcx, tcy = trk.center
            dist = math.hypot(dx - tcx, dy - tcy)

            # High IoU is an immediate strong match
            if iou >= 0.20 and iou > best_score:
                best_score = iou
                best_id = tid
            elif iou < 0.20 and dist < self.match_distance_threshold:
                # Proximity score (closer is better)
                prox_score = 1.0 - (dist / self.match_distance_threshold)
                if prox_score > best_score:
                    best_score = prox_score
                    best_id = tid

        return best_id

    def update(self, detections: List[Detection], current_time: float = None) -> List[TrackedObject]:
        """
        Update active tracks with new frame detections.
        
        Args:
            detections: List of Detection objects from Detector
            current_time: Optional explicit timestamp for offline video

        Returns:
            List of currently active TrackedObject instances
        """
        if current_time is None:
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
                # Update existing track
                track = self.tracks[tid]
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

        return [self.tracks[tid] for tid in active_ids if tid in self.tracks]

