"""
TrackState Module — Rolling Window Track Kinematics & Scale-Invariant Metrics
==============================================================================
Maintains per-track kinematic history, smoothed velocity vectors, scale-invariant
speed (bbox-heights/second), direction angles, and zone membership state.
"""
import time
import math
from collections import deque
from typing import Tuple, List, Set, Optional, Dict


class TrackState:
    """
    Rolling history and derived kinematics for a single tracked object across frames.
    Scale-invariant speed is computed by normalizing frame displacement against the
    object's bounding-box height, ensuring distance-invariant thresholding.
    """

    def __init__(self, track_id: int, object_type: str, object_label: str, max_history: int = 30):
        self.track_id: int = track_id
        self.object_type: str = object_type
        self.object_label: str = object_label
        self.max_history: int = max_history

        # Rolling history windows
        self.timestamps: deque = deque(maxlen=max_history)
        self.centroid_history: deque = deque(maxlen=max_history)      # (cx%, cy%)
        self.bottom_center_history: deque = deque(maxlen=max_history)  # (bx%, by%)
        self.bbox_history: deque = deque(maxlen=max_history)           # (w%, h%)

        # Kinematic state
        self.velocity: Tuple[float, float] = (0.0, 0.0)    # (vx_pct_per_s, vy_pct_per_s)
        self.speed_pct_s: float = 0.0                      # % of frame width per second
        self.speed_h_s: float = 0.0                        # scale-invariant: bbox-heights / second
        self.direction_deg: float = 0.0                    # 0 to 360 degrees (0 = right, 90 = down)
        self.acceleration_h_s2: float = 0.0                # scale-invariant acceleration

        # Zone & temporal state
        self.dwell_frames: int = 0
        self.first_seen: float = time.time()
        self.last_seen: float = time.time()
        self.zone_membership: Set[str] = set()
        self.zone_entry_times: Dict[str, float] = {}

    def update(self, bbox: dict, timestamp: Optional[float] = None) -> None:
        """
        Update rolling history and recompute smoothed kinematics.

        Args:
            bbox: Dict with {"x": float, "y": float, "w": float, "h": float} in % coordinates (0-100)
            timestamp: Epoch timestamp in seconds (defaults to time.time())
        """
        now = timestamp if timestamp is not None else time.time()
        cx = bbox["x"] + (bbox["w"] / 2.0)
        cy = bbox["y"] + (bbox["h"] / 2.0)
        bx = cx
        by = bbox["y"] + bbox["h"]
        w = max(0.1, bbox["w"])
        h = max(0.1, bbox["h"])

        self.timestamps.append(now)
        self.centroid_history.append((cx, cy))
        self.bottom_center_history.append((bx, by))
        self.bbox_history.append((w, h))
        self.last_seen = now
        self.dwell_frames += 1

        self._compute_kinematics()

    def _compute_kinematics(self) -> None:
        """Calculate smoothed velocity, scale-invariant speed, direction, and acceleration."""
        if len(self.timestamps) < 2:
            return

        dt = self.timestamps[-1] - self.timestamps[-2]
        if dt <= 0.0:
            return

        # Instantaneous displacement in % frame space
        dx = self.centroid_history[-1][0] - self.centroid_history[-2][0]
        dy = self.centroid_history[-1][1] - self.centroid_history[-2][1]

        inst_vx = dx / dt
        inst_vy = dy / dt

        # EMA smoothing (alpha = 0.35)
        alpha = 0.35
        prev_vx, prev_vy = self.velocity
        new_vx = alpha * inst_vx + (1.0 - alpha) * prev_vx
        new_vy = alpha * inst_vy + (1.0 - alpha) * prev_vy
        self.velocity = (new_vx, new_vy)

        # Speed in % frame space / s
        self.speed_pct_s = math.hypot(new_vx, new_vy)

        # Scale-Invariant Speed: Normalize displacement against bounding box height
        curr_h = self.bbox_history[-1][1]
        inst_speed_h_s = (math.hypot(dx, dy) / dt) / curr_h
        prev_speed_h_s = self.speed_h_s
        self.speed_h_s = alpha * inst_speed_h_s + (1.0 - alpha) * prev_speed_h_s

        # Acceleration spike (change in scale-invariant speed over dt)
        self.acceleration_h_s2 = (self.speed_h_s - prev_speed_h_s) / dt if dt > 0 else 0.0

        # Direction angle (0° = moving East/Right, 90° = South/Down, 180° = West/Left, 270° = North/Up)
        if self.speed_pct_s > 0.1:
            rad = math.atan2(new_vy, new_vx)
            deg = math.degrees(rad) % 360.0
            self.direction_deg = deg

    @property
    def current_centroid(self) -> Tuple[float, float]:
        """(cx%, cy%) centroid of current frame."""
        return self.centroid_history[-1] if self.centroid_history else (0.0, 0.0)

    @property
    def current_bottom_center(self) -> Tuple[float, float]:
        """(bx%, by%) bottom center of current frame."""
        return self.bottom_center_history[-1] if self.bottom_center_history else (0.0, 0.0)

    @property
    def current_bbox(self) -> dict:
        """Current bbox dictionary {"x", "y", "w", "h"}."""
        if not self.bbox_history or not self.centroid_history:
            return {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}
        cx, cy = self.centroid_history[-1]
        w, h = self.bbox_history[-1]
        return {"x": cx - w / 2.0, "y": cy - h / 2.0, "w": w, "h": h}

    def get_net_displacement_pct(self, window_seconds: float = 15.0) -> float:
        """
        Calculate total net displacement (% of frame width) over the last `window_seconds`.
        Used to differentiate loitering/lingering from straight-line passage.
        """
        if len(self.timestamps) < 2:
            return 0.0

        now = self.timestamps[-1]
        cutoff = now - window_seconds

        # Find earliest index within cutoff window
        start_idx = 0
        for i, ts in enumerate(self.timestamps):
            if ts >= cutoff:
                start_idx = i
                break

        start_cx, start_cy = self.centroid_history[start_idx]
        end_cx, end_cy = self.centroid_history[-1]
        return math.hypot(end_cx - start_cx, end_cy - start_cy)

    def update_zone_membership(self, active_zones: Set[str], timestamp: float) -> None:
        """Track entry times and zone presence per zone name."""
        # Check newly entered zones
        for zone in active_zones:
            if zone not in self.zone_membership:
                self.zone_entry_times[zone] = timestamp
        # Remove exited zones
        exited = self.zone_membership - active_zones
        for zone in exited:
            self.zone_entry_times.pop(zone, None)

        self.zone_membership = active_zones

    def zone_dwell_seconds(self, zone_name: str, current_time: float) -> float:
        """Return time spent inside a specific zone in seconds."""
        if zone_name in self.zone_entry_times:
            return max(0.0, current_time - self.zone_entry_times[zone_name])
        return 0.0
