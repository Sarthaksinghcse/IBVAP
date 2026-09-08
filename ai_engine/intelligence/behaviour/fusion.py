"""
Fusion & Alert Engine Module — Multi-Layer Rule Fusion & Rate Limiting
======================================================================
Combines Layer 1 interpretable rule primitives and Layer 2 unsupervised anomaly scores,
applies track-level cooldowns and global camera rate-limiting, crops forensic evidence
snapshots, and emits normalized alert payloads compatible with the FastAPI/DB schema.
"""
import os
import cv2
import time
import logging
from typing import List, Dict, Tuple, Optional
import numpy as np
from ai_engine.intelligence.behaviour.track_state import TrackState

logger = logging.getLogger("behaviour.fusion")

SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def escalate_severity(current_severity: str) -> str:
    """Escalate threat level by one tier (e.g. HIGH -> CRITICAL)."""
    try:
        idx = SEVERITY_ORDER.index(current_severity.upper())
        new_idx = min(len(SEVERITY_ORDER) - 1, idx + 1)
        return SEVERITY_ORDER[new_idx]
    except ValueError:
        return "HIGH"


class BehaviourAlertFusion:
    """Handles alert fusion, track-level deduplication cooldowns, and snapshot saving."""

    def __init__(self, cooldown_seconds: float = 20.0, global_rate_cap: int = 10, snapshot_dir: str = "storage/snapshots/behaviour"):
        self.cooldown_seconds: float = cooldown_seconds
        self.global_rate_cap: int = global_rate_cap
        self.snapshot_dir: str = snapshot_dir

        # State tracking for deduplication
        # (track_id, primitive_name) -> last_alert_time
        self.last_fired_times: Dict[Tuple[int, str], float] = {}

        # Global alert timestamp log for rate capping (rolling 60s)
        self.global_alert_history: List[float] = []

        # Ensure snapshot storage directory exists
        os.makedirs(self.snapshot_dir, exist_ok=True)

    def _is_on_cooldown(self, track_id: int, primitive_name: str, current_time: float) -> bool:
        """Check if a specific track + rule combination is within cooldown window."""
        key = (track_id, primitive_name)
        last_t = self.last_fired_times.get(key, 0.0)
        return (current_time - last_t) < self.cooldown_seconds

    def _check_global_rate_cap(self, current_time: float) -> bool:
        """Check if global alert count in last 60 seconds exceeds rate cap."""
        cutoff = current_time - 60.0
        self.global_alert_history = [t for t in self.global_alert_history if t >= cutoff]
        return len(self.global_alert_history) >= self.global_rate_cap

    def save_snapshot(
        self,
        frame: Optional[np.ndarray],
        bbox: dict,
        camera_id: str,
        track_id: int,
        timestamp: float
    ) -> Optional[str]:
        """Save a cropped frame evidence snapshot with 15% margin around bbox."""
        if frame is None or frame.size == 0 or not bbox:
            return None

        try:
            h, w = frame.shape[:2]
            bx = bbox.get("x", 0.0) / 100.0 * w
            by = bbox.get("y", 0.0) / 100.0 * h
            bw = bbox.get("w", 0.0) / 100.0 * w
            bh = bbox.get("h", 0.0) / 100.0 * h

            # 15% margin
            margin_x = bw * 0.15
            margin_y = bh * 0.15

            x1 = int(max(0, bx - margin_x))
            y1 = int(max(0, by - margin_y))
            x2 = int(min(w, bx + bw + margin_x))
            y2 = int(min(h, by + bh + margin_y))

            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                crop = frame

            filename = f"{camera_id}_{track_id}_{int(timestamp)}.jpg"
            filepath = os.path.join(self.snapshot_dir, filename)
            cv2.imwrite(filepath, crop)
            return filepath
        except Exception as e:
            logger.error(f"[Fusion] Failed to save snapshot: {e}")
            return None

    def fuse_and_build_alerts(
        self,
        camera_id: str,
        video_id: Optional[str],
        frame: Optional[np.ndarray],
        layer1_candidates: List[Tuple[TrackState, str, str, dict, str]], # (track, event_type, reason, evidence, severity)
        layer2_result: Tuple[float, str, dict],                          # (score, reason, evidence)
        timestamp: float
    ) -> List[dict]:
        """
        Fuse Layer 1 rules and Layer 2 score, apply cooldowns & rate caps, and build alert dicts.
        """
        l2_score, l2_reason, l2_evidence = layer2_result
        l2_fired = l2_score >= 3.0 and len(l2_reason) > 0

        final_alerts = []

        # 1. Process Layer 1 Fired Rules
        for track, event_type, reason, evidence, severity in layer1_candidates:
            primitive = evidence.get("primitive", event_type)

            if self._is_on_cooldown(track.track_id, primitive, timestamp):
                continue

            if self._check_global_rate_cap(timestamp):
                logger.warning(f"[Fusion] Global rate cap reached for {camera_id}. Suppressing alert.")
                break

            final_severity = severity
            final_reason = reason

            # Corroborate with Layer 2 anomaly score -> escalate severity
            if l2_fired:
                final_severity = escalate_severity(severity)
                final_reason += f" (Corroborated by unsupervised anomaly score {l2_score:.1f})"

            snapshot_path = self.save_snapshot(frame, track.current_bbox, camera_id, track.track_id, timestamp)

            alert_dict = {
                "camera_id": camera_id,
                "video_id": video_id,
                "event_type": event_type,
                "object_type": track.object_type,
                "object_id": track.object_label,
                "threat_level": final_severity,
                "reason": final_reason,
                "confidence": round(track.centroid_history[-1][0], 1) if track.centroid_history else 90.0,
                "bbox": track.current_bbox,
                "snapshot_path": snapshot_path,
                "evidence": evidence
            }

            self.last_fired_times[(track.track_id, primitive)] = timestamp
            self.global_alert_history.append(timestamp)
            final_alerts.append(alert_dict)

        # 2. Process Standalone Layer 2 Anomaly (if no Layer 1 rules fired)
        if l2_fired and not layer1_candidates:
            # Check global rate cap
            if not self._check_global_rate_cap(timestamp):
                dummy_track_id = 9999
                if not self._is_on_cooldown(dummy_track_id, "behaviour_anomaly", timestamp):
                    severity = "HIGH" if l2_score >= 5.0 else "MEDIUM"
                    alert_dict = {
                        "camera_id": camera_id,
                        "video_id": video_id,
                        "event_type": "BEHAVIOUR_ANOMALY",
                        "object_type": "UNSPECIFIED",
                        "object_id": "Anomaly Region",
                        "threat_level": severity,
                        "reason": f"Unsupervised Anomaly: {l2_reason}",
                        "confidence": 85.0,
                        "bbox": {"x": 25.0, "y": 25.0, "w": 50.0, "h": 50.0},
                        "snapshot_path": None,
                        "evidence": l2_evidence
                    }
                    self.last_fired_times[(dummy_track_id, "behaviour_anomaly")] = timestamp
                    self.global_alert_history.append(timestamp)
                    final_alerts.append(alert_dict)

        return final_alerts
