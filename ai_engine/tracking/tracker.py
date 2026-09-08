"""
IBVAP Object Tracker Module — ByteTrack Upgrade
=================================================
State-of-the-art Multi-Object Tracking (ByteTrack, Zhang et al. 2022).
Features:
- Kalman Filter with constant velocity model [cx, cy, a, h, v_cx, v_cy, v_a, v_h]
- Two-stage association:
    * Stage 1: Match high-confidence detections with Kalman-predicted tracks via IoU cost matrix
    * Stage 2: Match remaining unmatched tracks with low-confidence detections to preserve
      tracks through occlusions, motion blur, and viewpoint changes without false-track clutter
- Hungarian / Linear Sum Assignment matching with greedy fallback
- Smooth Kalman-filtered trajectory generation for behavioral intelligence
"""
import time
import math
import logging
from typing import List, Dict, Optional, Tuple
import numpy as np
from ai_engine.detection.detector import Detection

logger = logging.getLogger("tracker")

# Try to import scipy linear_sum_assignment for optimal Hungarian bipartite matching
try:
    from scipy.optimize import linear_sum_assignment
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    logger.warning("[Tracker] scipy not installed; falling back to greedy IoU assignment.")


class KalmanBoxTracker:
    """
    Kalman Filter for tracking bounding boxes in percentage coordinate space [0, 100].
    State vector: [cx, cy, a, h, v_cx, v_cy, v_a, v_h]^T
    where (cx, cy) is box center, a = w / h (aspect ratio), h is box height,
    and the remaining four components are their respective velocities.
    """
    count = 0

    def __init__(self, bbox: dict):
        """Initialize tracker with initial bounding box {"x", "y", "w", "h"}."""
        # Convert to [cx, cy, a, h]
        w = max(bbox["w"], 0.1)
        h = max(bbox["h"], 0.1)
        cx = bbox["x"] + w / 2.0
        cy = bbox["y"] + h / 2.0
        a = w / h

        # State vector [8, 1]
        self.x = np.array([[cx], [cy], [a], [h], [0.0], [0.0], [0.0], [0.0]], dtype=np.float32)

        # State transition matrix F (dt = 1)
        self.F = np.eye(8, dtype=np.float32)
        for i in range(4):
            self.F[i, i + 4] = 1.0

        # Measurement matrix H [4, 8]
        self.H = np.zeros((4, 8), dtype=np.float32)
        for i in range(4):
            self.H[i, i] = 1.0

        # Covariance matrix P
        self.P = np.diag([10.0, 10.0, 1.0, 10.0, 100.0, 100.0, 10.0, 100.0]).astype(np.float32)

        # Process noise covariance Q
        self.Q = np.diag([1.0, 1.0, 0.01, 1.0, 1.0, 1.0, 0.01, 1.0]).astype(np.float32) * 0.1

        # Measurement noise covariance R
        self.R = np.diag([1.0, 1.0, 0.1, 1.0]).astype(np.float32)

        self.time_since_update = 0
        self.hits = 1
        self.hit_streak = 1
        self.age = 0

    def predict(self) -> dict:
        """Advance the state vector and return the predicted bounding box."""
        # x' = F * x
        self.x = np.dot(self.F, self.x)
        # P' = F * P * F^T + Q
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q

        self.age += 1
        self.time_since_update += 1

        return self.get_bbox()

    def update(self, bbox: dict):
        """Update the state vector with observed bounding box measurement."""
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1

        w = max(bbox["w"], 0.1)
        h = max(bbox["h"], 0.1)
        cx = bbox["x"] + w / 2.0
        cy = bbox["y"] + h / 2.0
        a = w / h

        z = np.array([[cx], [cy], [a], [h]], dtype=np.float32)

        # Innovation: y = z - H * x
        y = z - np.dot(self.H, self.x)

        # Innovation covariance: S = H * P * H^T + R
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R

        # Kalman gain: K = P * H^T * inv(S)
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))

        # Updated state: x = x + K * y
        self.x = self.x + np.dot(K, y)

        # Updated covariance: P = (I - K * H) * P
        I = np.eye(8, dtype=np.float32)
        self.P = np.dot(I - np.dot(K, self.H), self.P)

    def get_bbox(self) -> dict:
        """Return current estimated bounding box in {"x", "y", "w", "h"} percentage space."""
        cx = float(self.x[0, 0])
        cy = float(self.x[1, 0])
        a = max(float(self.x[2, 0]), 0.05)
        h = max(float(self.x[3, 0]), 0.1)
        w = a * h

        x = max(0.0, min(100.0, cx - w / 2.0))
        y = max(0.0, min(100.0, cy - h / 2.0))
        w = max(0.1, min(100.0 - x, w))
        h = max(0.1, min(100.0 - y, h))

        return {"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)}


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
        self.zone_name: Optional[str] = None
        self.zone_entry_time: Optional[float] = None
        self.trajectory: List[Tuple[float, float]] = []  # List of (center_x, center_y) points

        # Kalman Filter model for ByteTrack state estimation
        self.kalman = KalmanBoxTracker(bbox)

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
    def bottom_center(self) -> Tuple[float, float]:
        """(x%, y%) bottom-center reference point for zone testing."""
        bx = self.bbox["x"] + (self.bbox["w"] / 2.0)
        by = self.bbox["y"] + self.bbox["h"]
        return (bx, by)

    @property
    def center(self) -> Tuple[float, float]:
        """(center_x%, center_y%) centroid coordinate."""
        cx = self.bbox["x"] + (self.bbox["w"] / 2.0)
        cy = self.bbox["y"] + (self.bbox["h"] / 2.0)
        return (cx, cy)


def compute_iou(boxA: dict, boxB: dict) -> float:
    """Compute Intersection over Union between two bounding boxes in % coordinates."""
    xA = max(boxA["x"], boxB["x"])
    yA = max(boxA["y"], boxB["y"])
    xB = min(boxA["x"] + boxA["w"], boxB["x"] + boxB["w"])
    yB = min(boxA["y"] + boxA["h"], boxB["y"] + boxB["h"])

    interW = max(0.0, xB - xA)
    interH = max(0.0, yB - yA)
    interArea = interW * interH

    boxAArea = max(boxA["w"] * boxA["h"], 1e-6)
    boxBArea = max(boxB["w"] * boxB["h"], 1e-6)
    unionArea = boxAArea + boxBArea - interArea

    if unionArea <= 0.0:
        return 0.0
    return float(interArea / unionArea)


def associate_detections_to_tracks(
    detections: List[Detection],
    tracks: List[TrackedObject],
    iou_threshold: float = 0.25
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """
    Assigns detections to tracked object using Hungarian algorithm on IoU cost matrix.
    Returns:
        matches: List of (det_idx, track_idx)
        unmatched_detections: List of det_idx
        unmatched_tracks: List of track_idx
    """
    if len(tracks) == 0:
        return [], list(range(len(detections))), []
    if len(detections) == 0:
        return [], [], list(range(len(tracks)))

    # Compute IoU cost matrix (cost = 1.0 - IoU)
    cost_matrix = np.zeros((len(detections), len(tracks)), dtype=np.float32)
    for d_idx, det in enumerate(detections):
        for t_idx, trk in enumerate(tracks):
            # Same class constraint: person only matches person, vehicle only vehicle
            if det.object_type != trk.object_type:
                cost_matrix[d_idx, t_idx] = 1.0  # Max cost
            else:
                iou = compute_iou(det.bbox, trk.bbox)
                cost_matrix[d_idx, t_idx] = 1.0 - iou

    matches: List[Tuple[int, int]] = []
    unmatched_dets = list(range(len(detections)))
    unmatched_trks = list(range(len(tracks)))

    if HAS_SCIPY:
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] <= (1.0 - iou_threshold):
                matches.append((int(r), int(c)))
                if r in unmatched_dets:
                    unmatched_dets.remove(r)
                if c in unmatched_trks:
                    unmatched_trks.remove(c)
    else:
        # Greedy fallback
        while True:
            min_val = np.min(cost_matrix)
            if min_val > (1.0 - iou_threshold):
                break
            r, c = np.unravel_index(np.argmin(cost_matrix), cost_matrix.shape)
            matches.append((int(r), int(c)))
            cost_matrix[r, :] = 1.0
            cost_matrix[:, c] = 1.0
            if r in unmatched_dets:
                unmatched_dets.remove(r)
            if c in unmatched_trks:
                unmatched_trks.remove(c)

    return matches, unmatched_dets, unmatched_trks


class Tracker:
    """
    ByteTrack: Multi-Object Tracker for IBVAP Surveillance Engine.
    Employs Kalman Filter spatial projection, 2-stage IoU association,
    and persistent ID maintenance across occlusions.
    """

    def __init__(
        self,
        track_thresh: float = 0.40,   # High-confidence detection threshold
        low_thresh: float = 0.15,     # Low-confidence detection threshold (for occlusion recovery)
        match_thresh: float = 0.25,   # Stage 1 IoU match threshold
        match_thresh_low: float = 0.20, # Stage 2 IoU match threshold
        max_lost_seconds: float = 4.0   # Time before a lost track is purged
    ):
        self.tracks: Dict[int, TrackedObject] = {}
        self.track_thresh = track_thresh
        self.low_thresh = low_thresh
        self.match_thresh = match_thresh
        self.match_thresh_low = match_thresh_low
        self.max_lost_seconds = max_lost_seconds
        self.next_id = 1
        self.yolo_to_stable_id: Dict[int, int] = {}

        logger.info(
            f"[Tracker] ByteTrack Object Tracker initialized | "
            f"HighThresh: {track_thresh} | LowThresh: {low_thresh} | MaxLost: {max_lost_seconds}s"
        )

    def update(self, detections: List[Detection]) -> List[TrackedObject]:
        """
        Update ByteTrack state with frame detections using 2-stage association.
        """
        current_time = time.time()

        # 1. Step Kalman Filter predictions for all existing tracks
        for tid, trk in self.tracks.items():
            predicted_bbox = trk.kalman.predict()
            # Update working bbox to Kalman prediction until measurement association
            trk.bbox = predicted_bbox

        # 2. Partition detections into High and Low confidence pools (ByteTrack Core)
        dets_high: List[Detection] = []
        dets_low: List[Detection] = []
        for det in detections:
            conf_norm = det.confidence / 100.0 if det.confidence > 1.0 else det.confidence
            if conf_norm >= self.track_thresh:
                dets_high.append(det)
            elif conf_norm >= self.low_thresh:
                dets_low.append(det)

        existing_track_list = list(self.tracks.values())
        active_ids = set()

        # ─── STAGE 1: Match High-Confidence Detections with Predicted Tracks ──────
        matches_1, unmatched_dets_1_idx, unmatched_tracks_1_idx = associate_detections_to_tracks(
            dets_high,
            existing_track_list,
            iou_threshold=self.match_thresh
        )

        for d_idx, t_idx in matches_1:
            det = dets_high[d_idx]
            trk = existing_track_list[t_idx]

            # Update Kalman with observation
            trk.kalman.update(det.bbox)
            trk.bbox = trk.kalman.get_bbox()
            trk.confidence = det.confidence
            trk.last_seen = current_time
            trk.frame_count += 1

            # Update ID mapping
            if det.track_id is not None:
                self.yolo_to_stable_id[det.track_id] = trk.track_id
            det.track_id = trk.track_id

            # Format label
            class_prefix = det.object_id.rsplit('#', 1)[0].strip() if '#' in det.object_id else det.object_type.title()
            det.object_id = f"{class_prefix} #{trk.track_id}"
            trk.object_label = det.object_id

            # Append to trajectory history
            trk.trajectory.append(trk.center)
            if len(trk.trajectory) > 60:
                trk.trajectory.pop(0)

            active_ids.add(trk.track_id)

        # ─── STAGE 2: Match Remaining Tracks with Low-Confidence Detections ───────
        unmatched_tracks_1 = [existing_track_list[idx] for idx in unmatched_tracks_1_idx]
        matches_2, _, unmatched_tracks_2_idx = associate_detections_to_tracks(
            dets_low,
            unmatched_tracks_1,
            iou_threshold=self.match_thresh_low
        )

        for d_idx, t_idx in matches_2:
            det = dets_low[d_idx]
            trk = unmatched_tracks_1[t_idx]

            # Recovered via low-confidence ByteTrack second association stage!
            trk.kalman.update(det.bbox)
            trk.bbox = trk.kalman.get_bbox()
            trk.confidence = det.confidence
            trk.last_seen = current_time
            trk.frame_count += 1

            if det.track_id is not None:
                self.yolo_to_stable_id[det.track_id] = trk.track_id
            det.track_id = trk.track_id

            class_prefix = det.object_id.rsplit('#', 1)[0].strip() if '#' in det.object_id else det.object_type.title()
            det.object_id = f"{class_prefix} #{trk.track_id}"
            trk.object_label = det.object_id

            trk.trajectory.append(trk.center)
            if len(trk.trajectory) > 60:
                trk.trajectory.pop(0)

            active_ids.add(trk.track_id)

        # ─── STAGE 3: Initialize New Tracks from Unmatched High-Conf Detections ───
        for d_idx in unmatched_dets_1_idx:
            det = dets_high[d_idx]
            raw_tid = det.track_id

            # Check if mapped previously
            if raw_tid is not None and raw_tid in self.yolo_to_stable_id and self.yolo_to_stable_id[raw_tid] in self.tracks:
                tid = self.yolo_to_stable_id[raw_tid]
                trk = self.tracks[tid]
                trk.kalman.update(det.bbox)
                trk.bbox = trk.kalman.get_bbox()
                trk.confidence = det.confidence
                trk.last_seen = current_time
                trk.frame_count += 1
                trk.trajectory.append(trk.center)
                active_ids.add(tid)
            else:
                tid = self.next_id
                self.next_id += 1
                if raw_tid is not None:
                    self.yolo_to_stable_id[raw_tid] = tid

                class_prefix = det.object_id.rsplit('#', 1)[0].strip() if '#' in det.object_id else det.object_type.title()
                label = f"{class_prefix} #{tid}"
                det.track_id = tid
                det.object_id = label

                new_track = TrackedObject(
                    track_id=tid,
                    object_type=det.object_type,
                    object_label=label,
                    bbox=det.bbox,
                    confidence=det.confidence
                )
                new_track.trajectory.append(new_track.center)
                self.tracks[tid] = new_track
                active_ids.add(tid)

        # ─── STAGE 4: Purge Lost Tracks Exceeding Max Lost Timeout ────────────────
        stale_threshold = current_time - self.max_lost_seconds
        stale_ids = [tid for tid, trk in self.tracks.items() if trk.last_seen < stale_threshold]
        for tid in stale_ids:
            del self.tracks[tid]
            keys_to_del = [k for k, v in self.yolo_to_stable_id.items() if v == tid]
            for k in keys_to_del:
                del self.yolo_to_stable_id[k]

        return [self.tracks[tid] for tid in active_ids if tid in self.tracks]


ByteTrackTracker = Tracker

