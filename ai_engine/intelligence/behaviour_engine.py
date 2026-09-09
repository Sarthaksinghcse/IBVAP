"""
IBVAP Behaviour Engine — Trajectory-Based Behavioral Analysis
================================================================
Analyzes rolling history of object centroids to evaluate movement dynamics:
velocity, path tortuosity, direction reversals, pacing, circling, and running.
"""
from collections import defaultdict, deque
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict
from enum import Enum

TRAJECTORY_BUFFER_FRAMES = 90   # ~3 seconds at 30fps
VELOCITY_WINDOW_FRAMES   = 15   # frames to compute current velocity over
MIN_TRAJECTORY_FRAMES    = 20   # don't analyze until we have enough history

@dataclass
class TrajectoryRecord:
    track_id: int = 0
    positions: deque = field(default_factory=lambda: deque(maxlen=TRAJECTORY_BUFFER_FRAMES))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=TRAJECTORY_BUFFER_FRAMES))

    def add(self, cx: float, cy: float, timestamp: float):
        self.positions.append((float(cx), float(cy)))
        self.timestamps.append(float(timestamp))

    @property
    def is_mature(self) -> bool:
        return len(self.positions) >= MIN_TRAJECTORY_FRAMES

    def current_velocity(self) -> float:
        """Pixels/second over the last VELOCITY_WINDOW_FRAMES frames."""
        if len(self.positions) < VELOCITY_WINDOW_FRAMES:
            return 0.0
        recent = list(self.positions)[-VELOCITY_WINDOW_FRAMES:]
        times  = list(self.timestamps)[-VELOCITY_WINDOW_FRAMES:]
        dx = recent[-1][0] - recent[0][0]
        dy = recent[-1][1] - recent[0][1]
        dt = times[-1] - times[0]
        if dt <= 0:
            return 0.0
        return float(np.sqrt(dx**2 + dy**2) / dt)  # px/sec

    def path_tortuosity(self) -> float:
        """
        Ratio of total path length to straight-line displacement.
        Tortuosity = 1.0 means perfectly straight.
        Tortuosity >> 1 means erratic/circular movement (surveillance behaviour).
        """
        pts = list(self.positions)
        if len(pts) < 2:
            return 1.0
        total_path = sum(
            float(np.sqrt((pts[i+1][0]-pts[i][0])**2 + (pts[i+1][1]-pts[i][1])**2))
            for i in range(len(pts)-1)
        )
        displacement = float(np.sqrt((pts[-1][0]-pts[0][0])**2 + (pts[-1][1]-pts[0][1])**2))
        if displacement < 1.0:
            return 999.0  # Stationary or nearly stationary displacement
        return total_path / displacement

    def direction_changes(self) -> int:
        """
        Count of significant direction reversals.
        High count = erratic / pacing behaviour.
        """
        pts = list(self.positions)
        if len(pts) < 3:
            return 0
        changes = 0
        for i in range(1, len(pts)-1):
            v1 = np.array([pts[i][0]-pts[i-1][0], pts[i][1]-pts[i-1][1]], dtype=float)
            v2 = np.array([pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1]], dtype=float)
            norm_v1 = np.linalg.norm(v1)
            norm_v2 = np.linalg.norm(v2)
            if norm_v1 > 0 and norm_v2 > 0:
                cos_theta = np.dot(v1, v2) / (norm_v1 * norm_v2)
                cos_theta = np.clip(cos_theta, -1.0, 1.0)
                angle = np.degrees(np.arccos(cos_theta))
                if angle > 90.0:   # reversal threshold
                    changes += 1
        return changes


class BehaviourLabel(str, Enum):
    NORMAL_TRANSIT    = "NORMAL_TRANSIT"      # moving through, no concern
    STATIONARY        = "STATIONARY"          # not moving (could be loitering)
    PACING            = "PACING"              # back-and-forth (reconnaissance)
    ERRATIC_MOVEMENT  = "ERRATIC_MOVEMENT"   # random path, many reversals
    RUNNING           = "RUNNING"             # high velocity — potential flee/chase
    CIRCLING          = "CIRCLING"            # high tortuosity, returns to same area


# Empirically-tuned thresholds (adjust per deployment environment)
VELOCITY_STATIONARY_THRESHOLD = 8.0     # px/sec
VELOCITY_RUNNING_THRESHOLD    = 120.0   # px/sec
TORTUOSITY_CIRCLING_THRESHOLD = 2.5     # ratio
DIRECTION_CHANGE_PACING_THRESHOLD = 4   # reversals in buffer window

BEHAVIOUR_THREAT_WEIGHT: Dict[BehaviourLabel, int] = {
    BehaviourLabel.NORMAL_TRANSIT:   0,
    BehaviourLabel.STATIONARY:       10,
    BehaviourLabel.PACING:           25,
    BehaviourLabel.ERRATIC_MOVEMENT: 20,
    BehaviourLabel.RUNNING:          30,
    BehaviourLabel.CIRCLING:         35,
}


class BehaviourEngine:
    def __init__(self):
        self._trajectories: Dict[int, TrajectoryRecord] = defaultdict(TrajectoryRecord)

    def update(self, track_id: int, cx: float, cy: float, timestamp: float) -> TrajectoryRecord:
        rec = self._trajectories[track_id]
        rec.track_id = track_id
        rec.add(cx, cy, timestamp)
        return rec

    def classify(self, track_id: int) -> Tuple[BehaviourLabel, float]:
        """Returns (BehaviourLabel, extra_threat_weight)."""
        rec = self._trajectories.get(track_id)
        if not rec or not rec.is_mature:
            return BehaviourLabel.NORMAL_TRANSIT, 0.0

        vel = rec.current_velocity()
        tort = rec.path_tortuosity()
        dir_changes = rec.direction_changes()

        if vel < VELOCITY_STATIONARY_THRESHOLD:
            label = BehaviourLabel.STATIONARY
        elif vel > VELOCITY_RUNNING_THRESHOLD:
            label = BehaviourLabel.RUNNING
        elif tort > TORTUOSITY_CIRCLING_THRESHOLD:
            label = BehaviourLabel.CIRCLING
        elif dir_changes >= DIRECTION_CHANGE_PACING_THRESHOLD:
            label = BehaviourLabel.PACING
        elif dir_changes >= 2:
            label = BehaviourLabel.ERRATIC_MOVEMENT
        else:
            label = BehaviourLabel.NORMAL_TRANSIT

        return label, float(BEHAVIOUR_THREAT_WEIGHT[label])

    def remove(self, track_id: int):
        self._trajectories.pop(track_id, None)


_behaviour_engine_instance: Optional[BehaviourEngine] = None

def get_behaviour_engine() -> BehaviourEngine:
    global _behaviour_engine_instance
    if _behaviour_engine_instance is None:
        _behaviour_engine_instance = BehaviourEngine()
    return _behaviour_engine_instance
