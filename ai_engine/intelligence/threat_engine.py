"""
IBVAP Threat Engine — Intelligence & Rule Evaluation
=====================================================
Analyzes tracked objects, evaluates restricted-zone polygons, detects loitering,
computes threat levels, applies false-positive filtering and alert deduplication,
and dispatches events to the FastAPI backend.
"""
import time
import logging
from typing import List, Dict, Optional, Tuple
import requests
from shapely.geometry import Point, Polygon
from ai_engine.tracking.tracker import TrackedObject
from ai_engine.intelligence.behaviour_engine import BehaviourEngine, BehaviourLabel, get_behaviour_engine

logger = logging.getLogger("threat_engine")

# Default Restricted Zone A matching the Web Portal left surveillance sector (percentages: 0-100)
DEFAULT_RESTRICTED_ZONE_A = [
    (5.0, 5.0),
    (50.0, 5.0),
    (50.0, 98.0),
    (5.0, 98.0)
]


class ThreatEngine:
    """
    Evaluates tracks against spatial and temporal security rules.
    Zones are attached strictly to the source camera / stream.
    If no zone is configured for this source, zone evaluation is disabled.
    """

    def __init__(
        self,
        camera_id: str = "BOP-07",
        backend_url: str = "http://127.0.0.1:8000",
        loitering_threshold: float = 30.0,
        restricted_zone_polygon: Optional[List[Tuple[float, float]]] = None,
        zone_name: Optional[str] = None,
        alert_cooldown_seconds: float = 20.0,
        min_confidence: float = 0.35,
        alert_callback: Optional[object] = None
    ):
        self.camera_id = camera_id
        self.backend_url = backend_url.rstrip("/")
        self.loitering_threshold = loitering_threshold  # seconds
        self.alert_cooldown_seconds = alert_cooldown_seconds
        self.min_confidence = min_confidence
        self.alert_callback = alert_callback
        self.behaviour_engine = get_behaviour_engine()

        # Configure Source-Specific Restricted Zone Polygon
        self.set_zone(restricted_zone_polygon, zone_name)

        # State tracking for deduplication and cooldowns
        # track_id -> last_alert_time
        self.last_alert_times: Dict[int, float] = {}
        # track_id -> highest_threat_sent
        self.highest_threat_sent: Dict[int, str] = {}
        # track_id -> loitering_alert_fired (bool)
        self.loitering_alert_fired: Dict[int, bool] = {}

        logger.info(
            f"[ThreatEngine] Initialized for {camera_id} | "
            f"Zone: {self.zone_name or 'None (disabled)'} | "
            f"Loiter limit: {loitering_threshold}s"
        )

    def set_zone(
        self,
        restricted_zone_polygon: Optional[List[Tuple[float, float]]],
        zone_name: Optional[str] = None
    ):
        """Update or clear the zone geometry for this camera source."""
        if restricted_zone_polygon and len(restricted_zone_polygon) >= 3:
            try:
                self.zone_polygon = Polygon(restricted_zone_polygon)
                self.zone_name = zone_name or "Restricted Zone A"
            except Exception as e:
                logger.error(f"[ThreatEngine] Error building zone polygon: {e}")
                self.zone_polygon = None
                self.zone_name = None
        else:
            self.zone_polygon = None
            self.zone_name = None


    def correlate_threat(
        self,
        track: TrackedObject,
        is_in_zone: bool,
        is_loitering: bool,
        video_id: Optional[str],
        behaviour_label: Optional[BehaviourLabel] = None,
        behaviour_weight: float = 0.0
    ) -> Tuple[str, str, str, dict]:
        """
        SIH Differentiator 1: Threat-Correlation Engine
        Combines zone-breach, loitering duration, detection confidence, trajectory behavior,
        time of day, and persistence into a single explainable threat assessment
        (NONE/LOW/MEDIUM/HIGH/CRITICAL) with stated evidence.
        """
        from datetime import datetime
        source_label = f"VIDEO {video_id}" if video_id else self.camera_id
        current_hour = datetime.now().hour
        is_night = (current_hour >= 22 or current_hour < 6)
        time_desc = "nighttime surveillance (high sensitivity)" if is_night else "daytime monitoring"

        b_label_str = behaviour_label.value if hasattr(behaviour_label, "value") else (str(behaviour_label) if behaviour_label else "NORMAL_TRANSIT")

        evidence = {
            "in_zone": is_in_zone,
            "zone_name": self.zone_name if is_in_zone else None,
            "dwell_sec": int(track.zone_dwell_time) if is_in_zone else int(track.dwell_time),
            "confidence": round(track.confidence, 1),
            "is_night": is_night,
            "frames_tracked": track.frame_count,
            "behaviour_label": b_label_str,
            "behaviour_weight": behaviour_weight,
        }

        # SIH Differentiator 2: False-Positive Filtering (Animals & Low Confidence)
        if track.confidence < (self.min_confidence * 100.0):
            return "FILTERED_LOW_CONFIDENCE", "NONE", f"Low confidence detection ({track.confidence:.1f}%) filtered.", evidence

        if track.object_type == "ANIMAL":
            return "ANIMAL_DETECTED", "NONE", f"Non-threat animal class ({track.object_label}) filtered from alert generation.", evidence

        # Person Threat Correlation
        if track.object_type == "PERSON":
            level = "LOW"
            event_type = "PERSON_DETECTED"
            reason_parts = [f"{track.object_label} detected at {source_label}."]

            if is_loitering and self.zone_name:
                event_type = "LOITERING"
                level = "CRITICAL"
                reason_parts = [
                    f"{track.object_label} breached {self.zone_name} at {source_label}, "
                    f"loitered for {int(track.zone_dwell_time)}s (limit: {int(self.loitering_threshold)}s), "
                    f"and maintained {track.confidence:.1f}% confidence during {time_desc}."
                ]
            elif is_in_zone and self.zone_name:
                event_type = "ZONE_INTRUSION"
                level = "CRITICAL" if is_night else "HIGH"
                reason_parts = [
                    f"{track.object_label} entered {self.zone_name} at {source_label} "
                    f"with {track.confidence:.1f}% confidence during {time_desc}."
                ]

            # Incorporate Trajectory Behaviour Analysis
            if behaviour_label == BehaviourLabel.RUNNING:
                reason_parts.append("Running detected (velocity-based, instant escalation).")
                if level in ["NONE", "LOW", "MEDIUM"]:
                    level = "HIGH"
            elif behaviour_label == BehaviourLabel.CIRCLING:
                reason_parts.append("Circular/surveillance movement pattern detected.")
                if level in ["NONE", "LOW", "MEDIUM"]:
                    level = "HIGH"
            elif behaviour_label == BehaviourLabel.PACING:
                reason_parts.append("Pacing behaviour (back-and-forth) detected.")
                if level in ["NONE", "LOW"]:
                    level = "MEDIUM"
            elif behaviour_label == BehaviourLabel.ERRATIC_MOVEMENT:
                reason_parts.append("Erratic movement pattern detected.")
                if level in ["NONE", "LOW"]:
                    level = "MEDIUM"

            return event_type, level, " ".join(reason_parts), evidence

        # Vehicle Threat Correlation
        elif track.object_type == "VEHICLE":
            if is_in_zone and self.zone_name:
                reason = (
                    f"{track.object_label} unauthorized entry into {self.zone_name} at {source_label} "
                    f"with {track.confidence:.1f}% confidence."
                )
                return "ZONE_INTRUSION", "CRITICAL", reason, evidence
            else:
                return "VEHICLE_DETECTED", "MEDIUM", f"{track.object_label} detected at {source_label}.", evidence

        return "OBJECT_DETECTED", "NONE", f"{track.object_label} observed at {source_label}.", evidence

    def process_tracks(self, tracks: List[TrackedObject], video_id: Optional[str] = None, frame_bgr: Optional[object] = None) -> List[dict]:
        """
        Evaluate all currently active tracks in the frame using the Threat-Correlation Engine.
        Generates detection events and dispatches alerts when correlated threat conditions are met.
        """
        current_time = time.time()
        processed_detections = []

        # Clean up stale/lost tracks in trajectory store
        active_ids = {t.track_id for t in tracks}
        for stored_id in list(self.behaviour_engine._trajectories.keys()):
            if stored_id not in active_ids:
                self.behaviour_engine.remove(stored_id)

        for track in tracks:
            bx, by = track.bottom_center
            pt = Point(bx, by)

            # Update Trajectory Store & Behavior Engine
            cx = float(track.bbox.get("x", 0.0) + track.bbox.get("w", 0.0) / 2.0)
            cy = float(track.bbox.get("y", 0.0) + track.bbox.get("h", 0.0) / 2.0)
            self.behaviour_engine.update(track.track_id, cx, cy, current_time)
            behaviour_label, behaviour_weight = self.behaviour_engine.classify(track.track_id)
            b_label_str = behaviour_label.value if hasattr(behaviour_label, "value") else str(behaviour_label)

            # 1. Evaluate Restricted Zone Geometry (Source-Specific)
            is_in_zone = False
            if self.zone_polygon is not None:
                try:
                    is_in_zone = self.zone_polygon.contains(pt)
                except Exception as e:
                    logger.error(f"[ThreatEngine] Zone check error: {e}")

            # 2. Update Spatial State on Track Object
            track.update_zone_status(is_in_zone)
            zone_dwell = track.zone_dwell_time
            is_loitering = (zone_dwell >= self.loitering_threshold)

            # Evaluate ANPR for vehicle tracks if frame is provided
            plate_info = None
            if track.object_type == "VEHICLE" and frame_bgr is not None:
                try:
                    from ai_engine.intelligence.anpr_engine import get_anpr_engine
                    anpr_eng = get_anpr_engine()
                    plate_info = anpr_eng.evaluate_vehicle_plate(
                        frame_bgr=frame_bgr,
                        vehicle_bbox=track.bbox,
                        camera_id=self.camera_id,
                        track_id=track.track_id,
                        vehicle_type=track.object_label.split(" ")[0].upper() if " " in track.object_label else "CAR"
                    )
                except Exception as anpr_err:
                    logger.debug(f"[ThreatEngine] ANPR error: {anpr_err}")

            # 3. SIH Differentiator 1: Run Multi-Factor Threat Correlation
            event_type, threat_level, reason, evidence = self.correlate_threat(
                track=track,
                is_in_zone=is_in_zone,
                is_loitering=is_loitering,
                video_id=video_id,
                behaviour_label=behaviour_label,
                behaviour_weight=behaviour_weight
            )

            # If plate is detected, reflect in event_type if not higher-priority zone intrusion
            if not is_in_zone and plate_info:
                if plate_info.get("plate_status") == "READABLE":
                    event_type = "PLATE_DETECTED"
                elif plate_info.get("plate_status") == "UNREADABLE":
                    event_type = "UNREADABLE_PLATE"

            # 4. Build Detection Event Payload
            det_payload = {
                "camera_id": self.camera_id,
                "video_id": video_id,
                "object_type": track.object_type,
                "object_id": track.object_label,
                "confidence": round(track.confidence, 1),
                "zone": self.zone_name if is_in_zone else None,
                "event_type": event_type,
                "bbox": track.bbox,
                "is_in_restricted_zone": is_in_zone,
                "loitering_duration": int(zone_dwell) if is_in_zone else None,
                "plate_info": plate_info,
                "behaviour_label": b_label_str,
            }

            # 5. POST Detection Event to FastAPI (Detection != Alert)
            self.post_detection(det_payload)
            processed_detections.append(det_payload)

            # 6. Evaluate Whether to Trigger an ALERT (with Cooldown / Deduplication & Confidence check)
            is_confident = (track.confidence >= (self.min_confidence * 100.0))
            if threat_level in ["HIGH", "CRITICAL"] and is_confident:
                should_alert = self._should_fire_alert(
                    track_id=track.track_id,
                    threat_level=threat_level,
                    is_loitering=is_loitering,
                    current_time=current_time
                )


                if should_alert:
                    alert_payload = {
                        "camera_id": self.camera_id,
                        "video_id": video_id,
                        "event_type": event_type,
                        "object_type": track.object_type,
                        "object_id": track.object_label,
                        "threat_level": threat_level,
                        "reason": reason,
                        "confidence": round(track.confidence, 1),
                        "bbox": track.bbox,
                    }
                    if self.alert_callback:
                        try:
                            self.alert_callback(alert_payload)
                        except Exception as cb_err:
                            logger.error(f"[ThreatEngine] alert_callback error: {cb_err}")
                    else:
                        self.post_alert(alert_payload)

                    self.last_alert_times[track.track_id] = current_time
                    self.highest_threat_sent[track.track_id] = threat_level
                    if is_loitering:
                        self.loitering_alert_fired[track.track_id] = True


        return processed_detections

    def _should_fire_alert(self, track_id: int, threat_level: str, is_loitering: bool, current_time: float) -> bool:
        """
        Deduplication rule to prevent alert spam:
        - Send on first zone entry.
        - Send when threat escalates to CRITICAL (loitering threshold breached).
        - Allow re-alert only after alert_cooldown_seconds have passed.
        """
        last_time = self.last_alert_times.get(track_id, 0.0)
        highest_threat = self.highest_threat_sent.get(track_id, "NONE")
        loitering_already_fired = self.loitering_alert_fired.get(track_id, False)

        # First alert for this track
        if last_time == 0.0:
            return True

        # Escalation from HIGH to CRITICAL (Loitering triggered)
        if threat_level == "CRITICAL" and highest_threat != "CRITICAL" and not loitering_already_fired:
            return True

        # Periodic reminder alert after cooldown has elapsed
        if (current_time - last_time) >= self.alert_cooldown_seconds:
            return True

        return False

    # CALLED FROM: pipeline.py (Phase 2), videos.py (Phase 4.3)
    def trigger_watchlist_alert(
        self,
        person_id: str,
        person_name: str,
        identifier: Optional[str],
        threat_priority: str,
        similarity: float,
        cosine_score: float,
        track_id: Optional[int],
        bbox: dict,
        is_in_zone: bool = False,
        video_id: Optional[str] = None
    ) -> bool:
        """
        Processes a confirmed real Watchlist Match from the FaceEngine.
        Evaluates threat severity rules and applies deduplication cooldown before firing alert.
        """
        current_time = time.time()
        dedup_key = f"watchlist:{person_id}:{track_id}" if track_id is not None else f"watchlist:{person_id}"
        # Phase 1.5 (I3): Key on string directly — hash() discards information
        last_alert = self.last_alert_times.get(dedup_key, 0.0)

        if (current_time - last_alert) < self.alert_cooldown_seconds:
            # Suppress duplicate alert within cooldown window
            return False

        # Threat Severity Rules (Documented as per requirements):
        # 1. If target is inside a restricted zone -> Escalate to CRITICAL immediately
        # 2. If target has priority CRITICAL in DB -> CRITICAL
        # 3. Otherwise use the person's configured priority (HIGH / MEDIUM / LOW)
        if is_in_zone and self.zone_name:
            threat_level = "CRITICAL"
            reason = (
                f"WATCHLIST MATCH IN RESTRICTED ZONE: {person_name} "
                f"({identifier or 'Target ID: ' + person_id[:8]}) detected inside {self.zone_name} "
                f"at {self.camera_id} with {similarity:.1f}% face match confidence."
            )
        elif threat_priority == "CRITICAL":
            threat_level = "CRITICAL"
            reason = (
                f"CRITICAL WATCHLIST TARGET IDENTIFIED: {person_name} "
                f"({identifier or 'Target ID: ' + person_id[:8]}) spotted at {self.camera_id} "
                f"with {similarity:.1f}% face match confidence."
            )
        elif threat_priority == "HIGH":
            threat_level = "HIGH"
            reason = (
                f"WATCHLIST TARGET IDENTIFIED: {person_name} "
                f"({identifier or 'Target ID: ' + person_id[:8]}) spotted at {self.camera_id} "
                f"with {similarity:.1f}% face match confidence."
            )
        elif threat_priority == "MEDIUM":
            threat_level = "MEDIUM"
            reason = (
                f"Watchlist person {person_name} spotted at {self.camera_id} "
                f"with {similarity:.1f}% face match confidence."
            )
        else:
            threat_level = "LOW"
            reason = (
                f"Watchlist target {person_name} logged at {self.camera_id} "
                f"with {similarity:.1f}% face match confidence."
            )

        alert_payload = {
            "camera_id": self.camera_id,
            "video_id": video_id,
            "event_type": "WATCHLIST_MATCH",
            "object_type": "PERSON",
            "object_id": f"{person_name} ({'Track #' + str(track_id) if track_id else 'Person'})",
            "threat_level": threat_level,
            "reason": reason,
            "confidence": similarity,
            "bbox": bbox,
        }

        if self.alert_callback:
            try:
                self.alert_callback(alert_payload)
            except Exception as cb_err:
                logger.error(f"[ThreatEngine] alert_callback error for watchlist: {cb_err}")
        else:
            self.post_alert(alert_payload)

        self.last_alert_times[dedup_key] = current_time
        logger.warning(f"[ThreatEngine] Fired WATCHLIST_MATCH Alert for {person_name} at {self.camera_id} ({threat_level})")
        return True

    def post_alert(self, alert_data: dict) -> bool:
        """Send alert to FastAPI backend to trigger DB save and WebSocket broadcast."""
        try:
            r = requests.post(
                f"{self.backend_url}/api/alerts/",
                json=alert_data,
                timeout=5,
            )
            if r.status_code == 200:
                logger.info(f"[ThreatEngine] Alert posted successfully: {alert_data.get('event_type')} - {alert_data.get('threat_level')}")
                return True
            else:
                logger.warning(f"[ThreatEngine] Alert post returned status {r.status_code}: {r.text}")
                return False
        except Exception as e:
            logger.error(f"[ThreatEngine] Failed to post alert: {e}")
            return False

    def post_detection(self, det_data: dict) -> bool:
        """Send detection event to FastAPI backend."""
        try:
            r = requests.post(
                f"{self.backend_url}/api/detections/",
                json=det_data,
                timeout=5,
            )
            return r.status_code == 200
        except Exception as e:
            logger.debug(f"[ThreatEngine] Failed to post detection: {e}")
            return False

