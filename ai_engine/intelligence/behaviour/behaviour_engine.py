"""
IBVAP BehaviourEngine — Main Orchestration & Entry Point
=========================================================
Public entry point for the behaviour analysis system. Manages TrackState persistence,
evaluates Layer 1 rule primitives and Layer 2 unsupervised grid anomaly scoring, fuses
alerts via BehaviourAlertFusion, and respects the IBVAP_BEHAVIOUR_ENABLED environment flag.
"""
import os
import time
import yaml
import logging
from typing import List, Dict, Optional, Tuple
import numpy as np

from ai_engine.tracking.tracker import TrackedObject
from ai_engine.intelligence.behaviour.track_state import TrackState
from ai_engine.intelligence.behaviour.zones import ZoneManager
from ai_engine.intelligence.behaviour.anomaly import GridAnomalyModel
from ai_engine.intelligence.behaviour.fusion import BehaviourAlertFusion
from ai_engine.intelligence.behaviour import primitives

logger = logging.getLogger("behaviour_engine")


class BehaviourEngine:
    """
    Main Behaviour Intelligence Subsystem.
    Consumes tracked objects per frame and outputs verified, explainable alert payloads.
    """

    def __init__(
        self,
        config_path: str = "ai_engine/intelligence/behaviour/config/behaviour.yaml",
        enabled: Optional[bool] = None
    ):
        # 1. Environment Flag Evaluation (R4 & §2.4)
        if enabled is not None:
            self.enabled: bool = enabled
        else:
            env_val = os.getenv("IBVAP_BEHAVIOUR_ENABLED", "1").strip().lower()
            self.enabled = env_val not in ("0", "false", "no", "off")

        self.config_path: str = config_path
        self.config: dict = self._load_config(config_path)

        # Module enable check from YAML config
        if not self.config.get("enabled", True):
            self.enabled = False

        # TrackState persistence per track_id
        self.track_states: Dict[int, TrackState] = {}

        # Subsystems
        cam_configs = self.config.get("cameras", {})
        self.zone_manager: ZoneManager = ZoneManager(cam_configs)

        anom_cfg = self.config.get("anomaly", {})
        self.anomaly_model: GridAnomalyModel = GridAnomalyModel(
            rows=anom_cfg.get("grid_rows", 8),
            cols=anom_cfg.get("grid_cols", 8),
            learning_rate=anom_cfg.get("learning_rate", 0.01),
            threshold=anom_cfg.get("score_threshold", 3.0)
        )

        cooldown = self.config.get("debounce_cooldown_seconds", 20.0)
        rate_cap = self.config.get("global_rate_cap_per_min", 10)
        self.fusion: BehaviourAlertFusion = BehaviourAlertFusion(
            cooldown_seconds=cooldown,
            global_rate_cap=rate_cap
        )

        logger.info(
            f"[BehaviourEngine] Initialized | Enabled: {self.enabled} | "
            f"Anomaly Grid: {anom_cfg.get('grid_rows', 8)}x{anom_cfg.get('grid_cols', 8)} | "
            f"Cooldown: {cooldown}s"
        )

    def _load_config(self, path: str) -> dict:
        """Load YAML configuration file or return default fallback config."""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"[BehaviourEngine] Error reading {path}: {e}")
        return {}

    def process(
        self,
        camera_id: str,
        frame: Optional[np.ndarray],
        tracks: List[TrackedObject],
        timestamp: Optional[float] = None,
        video_id: Optional[str] = None
    ) -> List[dict]:
        """
        Process frame tracks and evaluate behaviour rules and anomaly scoring.

        Args:
            camera_id: Camera identifier (e.g. "BOP-07")
            frame: Optional BGR frame numpy array (for evidence snapshot cropping)
            tracks: List of TrackedObject instances from Tracker
            timestamp: Epoch timestamp float
            video_id: Optional video identifier in DB

        Returns:
            List of alert dictionaries adhering to AlertCreate schema
        """
        # Fast exit if module is disabled via env flag or config
        if not self.enabled:
            return []

        now = timestamp if timestamp is not None else time.time()
        active_ids = set()
        active_states: List[TrackState] = []

        # 1. Update / Instantiate TrackState for active tracks
        for trk in tracks:
            tid = trk.track_id
            active_ids.add(tid)

            if tid not in self.track_states:
                self.track_states[tid] = TrackState(
                    track_id=tid,
                    object_type=trk.object_type,
                    object_label=trk.object_label
                )

            st = self.track_states[tid]
            st.update(trk.bbox, timestamp=now)

            # Update zone membership for this track
            matching_zones = self.zone_manager.evaluate_point(camera_id, st.current_bottom_center)
            zone_names = {z.name for z in matching_zones}
            st.update_zone_membership(zone_names, timestamp=now)

            active_states.append(st)

        # Clean up stale track states
        stale_tids = [tid for tid in self.track_states if tid not in active_ids]
        for tid in stale_tids:
            del self.track_states[tid]

        if not active_states:
            # Still run anomaly model background update if needed
            self.anomaly_model.evaluate_and_update([], freeze_update=False)
            return []

        zones = self.zone_manager.get_zones_for_camera(camera_id)
        prim_cfg = self.config.get("primitives", {})
        night_hours_cfg = self.config.get("night_hours", {})

        layer1_candidates = []  # List of (track, event_type, reason, evidence, severity)

        # 2. Evaluate Layer 1 Behaviour Primitives per Track
        for st in active_states:

            # P1: Zone Intrusion / Virtual Fence
            p1_cfg = prim_cfg.get("zone_intrusion", {})
            if p1_cfg.get("enabled", True):
                fired, reason, evidence = primitives.check_zone_intrusion(st, zones, p1_cfg, now)
                if fired:
                    layer1_candidates.append((st, "ZONE_INTRUSION", reason, evidence, p1_cfg.get("severity", "HIGH")))

            # P2: Loitering
            p2_cfg = prim_cfg.get("loitering", {})
            if p2_cfg.get("enabled", True):
                fired, reason, evidence = primitives.check_loitering(st, zones, p2_cfg, now)
                if fired:
                    layer1_candidates.append((st, "LOITERING", reason, evidence, p2_cfg.get("severity", "MEDIUM")))

            # P3: Direction Violation
            p3_cfg = prim_cfg.get("direction_violation", {})
            if p3_cfg.get("enabled", True):
                fired, reason, evidence = primitives.check_direction_violation(st, zones, p3_cfg, now)
                if fired:
                    layer1_candidates.append((st, "DIRECTION_VIOLATION", reason, evidence, p3_cfg.get("severity", "HIGH")))

            # P4: Speed Anomaly (Running / Sprinting)
            p4_cfg = prim_cfg.get("speed_anomaly", {})
            if p4_cfg.get("enabled", True):
                fired, reason, evidence = primitives.check_speed_anomaly(st, zones, p4_cfg, now)
                if fired:
                    layer1_candidates.append((st, "SPEED_ANOMALY", reason, evidence, p4_cfg.get("severity", "MEDIUM")))

            # P6: Night Presence
            p6_cfg = prim_cfg.get("night_presence", {})
            if p6_cfg.get("enabled", True):
                fired, reason, evidence = primitives.check_night_presence(st, night_hours_cfg, p6_cfg, now)
                if fired:
                    layer1_candidates.append((st, "NIGHT_MOVEMENT", reason, evidence, p6_cfg.get("severity", "HIGH")))

        # P5: Group Formation (Evaluated across all active tracks simultaneously)
        p5_cfg = prim_cfg.get("group_formation", {})
        if p5_cfg.get("enabled", True):
            group_results = primitives.check_group_formation(active_states, zones, p5_cfg, now)
            for fired, reason, evidence in group_results:
                if fired and active_states:
                    first_st = active_states[0]
                    layer1_candidates.append((first_st, "GROUP_FORMATION", reason, evidence, p5_cfg.get("severity", "HIGH")))

        # 3. Evaluate Layer 2 Unsupervised Anomaly Scoring
        freeze_anomaly = len(layer1_candidates) > 0
        score, a_reason, a_evidence, _ = self.anomaly_model.evaluate_and_update(
            active_states,
            freeze_update=freeze_anomaly
        )
        l2_result = (score, a_reason, a_evidence)

        # 4. Alert Fusion, Cooldown & Snapshot Emission
        alerts = self.fusion.fuse_and_build_alerts(
            camera_id=camera_id,
            video_id=video_id,
            frame=frame,
            layer1_candidates=layer1_candidates,
            layer2_result=l2_result,
            timestamp=now
        )

        return alerts

    def get_anomaly_heatmap(self) -> np.ndarray:
        """Return the current 8x8 grid anomaly heatmap array."""
        return self.anomaly_model.current_heatmap
