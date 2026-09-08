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
        alert_callback: Optional[object] = None,
        detection_callback: Optional[object] = None
    ):
        self.camera_id = camera_id
        self.backend_url = backend_url.rstrip("/")
        self.loitering_threshold = loitering_threshold  # seconds
        self.alert_cooldown_seconds = alert_cooldown_seconds
        self.min_confidence = min_confidence
        self.alert_callback = alert_callback
        self.detection_callback = detection_callback



        # State tracking for deduplication, cooldowns, and spatial transitions
        self.active_zone_tracks: set = set()
        self.last_seen_in_zone: Dict[int, float] = {}
        # track_id -> last_alert_time
        self.last_alert_times: Dict[int, float] = {}
        # track_id -> highest_threat_sent
        self.highest_threat_sent: Dict[int, str] = {}
        # track_id -> loitering_alert_fired (bool)
        self.loitering_alert_fired: Dict[int, bool] = {}

        # Configure Source-Specific Restricted Zone Polygon
        self.zone_coords: Optional[List[Tuple[float, float]]] = None
        self.set_zone(restricted_zone_polygon, zone_name)

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
        """Update or clear the zone geometry for this camera source with coordinate normalization."""
        if restricted_zone_polygon and len(restricted_zone_polygon) >= 3:
            # Check if coordinates are normalized 0.0 - 1.0 and scale to 0 - 100% if needed
            max_val = max(max(float(pt[0]), float(pt[1])) for pt in restricted_zone_polygon)
            if max_val <= 1.05:
                normalized_coords = [(float(pt[0]) * 100.0, float(pt[1]) * 100.0) for pt in restricted_zone_polygon]
            else:
                normalized_coords = [(float(pt[0]), float(pt[1])) for pt in restricted_zone_polygon]

            self.zone_coords = normalized_coords
            try:
                self.zone_polygon = Polygon(self.zone_coords)
                self.zone_name = zone_name or "Restricted Zone A"
            except Exception as e:
                logger.error(f"[ThreatEngine] Error building zone polygon: {e}")
                self.zone_polygon = None
                self.zone_name = None
        else:
            self.zone_coords = None
            self.zone_polygon = None
            self.zone_name = None


    def correlate_threat(
        self,
        track: TrackedObject,
        is_in_zone: bool,
        is_loitering: bool,
        video_id: Optional[str]
    ) -> Tuple[str, str, str, dict]:
        """
        SIH Differentiator 1: Threat-Correlation Engine
        Combines zone-breach, loitering duration, detection confidence, time of day,
        and persistence into a single explainable threat assessment (NONE/LOW/MEDIUM/HIGH/CRITICAL)
        with stated evidence.
        """
        from datetime import datetime
        source_label = f"VIDEO {video_id}" if video_id else self.camera_id
        current_hour = datetime.now().hour
        is_night = (current_hour >= 22 or current_hour < 6)
        time_desc = "nighttime surveillance (high sensitivity)" if is_night else "daytime monitoring"

        evidence = {
            "in_zone": is_in_zone,
            "zone_name": self.zone_name if is_in_zone else None,
            "dwell_sec": int(track.zone_dwell_time) if is_in_zone else int(track.dwell_time),
            "confidence": round(track.confidence, 1),
            "is_night": is_night,
            "frames_tracked": track.frame_count,
        }

        # SIH Differentiator 2: False-Positive Filtering (Animals & Low Confidence)
        if track.confidence < (self.min_confidence * 100.0):
            return "FILTERED_LOW_CONFIDENCE", "NONE", f"Low confidence detection ({track.confidence:.1f}%) filtered.", evidence

        is_animal = track.object_type in ["ANIMAL", "DOG", "CAT", "BIRD", "HORSE", "SHEEP", "COW", "ELEPHANT", "BEAR", "ZEBRA", "GIRAFFE"]
        if is_animal:
            return f"{track.object_type}_DETECTED", "NONE", f"Non-threat animal class ({track.object_label}) observed at {source_label}.", evidence

        # Person Threat Correlation
        if track.object_type == "PERSON":
            if is_loitering and self.zone_name:
                reason = (
                    f"{track.object_label} breached {self.zone_name} at {source_label}, "
                    f"loitered for {int(track.zone_dwell_time)}s (limit: {int(self.loitering_threshold)}s), "
                    f"and maintained {track.confidence:.1f}% confidence during {time_desc}."
                )
                return "LOITERING", "CRITICAL", reason, evidence

            elif is_in_zone and self.zone_name:
                level = "CRITICAL" if is_night else "HIGH"
                reason = (
                    f"{track.object_label} entered {self.zone_name}."
                )
                return "ZONE_INTRUSION", level, reason, evidence

            else:
                return "PERSON_DETECTED", "LOW", f"{track.object_label} detected at {source_label}.", evidence

        # Vehicle Threat Correlation
        elif track.object_type in ["VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE", "BICYCLE"]:
            if is_in_zone and self.zone_name:
                reason = (
                    f"{track.object_label} entered {self.zone_name}."
                )
                return "ZONE_INTRUSION", "CRITICAL", reason, evidence
            else:
                return f"{track.object_type}_DETECTED", "MEDIUM", f"{track.object_label} detected at {source_label}.", evidence

        return "OBJECT_DETECTED", "NONE", f"{track.object_label} observed at {source_label}.", evidence

    def process_tracks(self, tracks: List[TrackedObject], video_id: Optional[str] = None, frame_bgr: Optional[object] = None) -> List[dict]:
        """
        Evaluate all currently active tracks in the frame using the Threat-Correlation Engine.
        Generates detection events and dispatches alerts when correlated threat conditions are met.
        """
        current_time = time.time()
        processed_detections = []
        logger.info(f"[THREAT] Processing {len(tracks)} tracks for camera {self.camera_id}")

        for track in tracks:
            bx, by = track.bottom_center
            pt = Point(bx, by)

            # 1. Evaluate Restricted Zone Geometry (Source-Specific)
            is_in_zone = False
            if self.zone_polygon is not None:
                try:
                    is_in_zone = self.zone_polygon.contains(pt) or self.zone_polygon.touches(pt)
                except Exception as e:
                    logger.error(f"[ThreatEngine] Zone check error: {e}")

            # 2. Update Spatial State on Track Object
            track.update_zone_status(is_in_zone, self.zone_name)
            zone_dwell = track.zone_dwell_time
            is_loitering = (zone_dwell >= self.loitering_threshold)
            logger.info(f"[ZONE] track_id={track.track_id} label={track.object_label} inside={is_in_zone}")

            # Evaluate ANPR for vehicle tracks if frame is provided
            plate_info = None
            if track.object_type in ["VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE"] and frame_bgr is not None:
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
                video_id=video_id
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
            }

            # 5. Emit Detection Event to Callback or FastAPI (Detection != Alert)
            if self.detection_callback:
                try:
                    self.detection_callback(det_payload)
                except Exception as dcb_err:
                    logger.debug(f"[ThreatEngine] detection_callback error: {dcb_err}")
            elif not self.alert_callback:
                # Only post via HTTP if no in-process callbacks attached
                self.post_detection(det_payload)
            processed_detections.append(det_payload)

            # 6. Evaluate Whether to Trigger an ALERT (Transition OUTSIDE -> INSIDE, No spam while inside)
            is_confident = (track.confidence >= (self.min_confidence * 100.0))
            is_threat_target = track.object_type in ["PERSON", "VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE", "BICYCLE"]

            if is_confident and is_threat_target and self.zone_name:
                if is_in_zone:
                    self.last_seen_in_zone[track.track_id] = current_time
                    is_new_entry = (track.track_id not in self.active_zone_tracks)

                    if is_new_entry:
                        self.active_zone_tracks.add(track.track_id)
                        logger.info(f"[THREAT] event=ZONE_INTRUSION track_id={track.track_id} {track.object_label}")

                        alert_payload = {
                            "camera_id": self.camera_id,
                            "video_id": video_id,
                            "event_type": "ZONE_INTRUSION",
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

                        logger.info(f"[ALERT] camera={self.camera_id} event=ZONE_INTRUSION level={threat_level} reason='{reason}'")
                        self.last_alert_times[track.track_id] = current_time
                        self.highest_threat_sent[track.track_id] = threat_level

                    elif is_loitering and not self.loitering_alert_fired.get(track.track_id, False):
                        # Escalate to LOITERING alert once while inside
                        self.loitering_alert_fired[track.track_id] = True
                        loiter_reason = f"{track.object_label} breached {self.zone_name} and loitered for {int(zone_dwell)}s."
                        logger.info(f"[THREAT] event=LOITERING track_id={track.track_id} {track.object_label}")

                        alert_payload = {
                            "camera_id": self.camera_id,
                            "video_id": video_id,
                            "event_type": "LOITERING",
                            "object_type": track.object_type,
                            "object_id": track.object_label,
                            "threat_level": "CRITICAL",
                            "reason": loiter_reason,
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

                        logger.info(f"[ALERT] camera={self.camera_id} event=LOITERING level=CRITICAL reason='{loiter_reason}'")
                        self.last_alert_times[track.track_id] = current_time
                        self.highest_threat_sent[track.track_id] = "CRITICAL"
                else:
                    # Outside zone - track transition back to outside
                    if track.track_id in self.active_zone_tracks:
                        self.active_zone_tracks.remove(track.track_id)
                        self.loitering_alert_fired.pop(track.track_id, None)
                        logger.info(f"[ZONE] track_id={track.track_id} exited {self.zone_name} (state returns outside)")

        # Cleanup tracks that disappeared from camera view for > 4.0 seconds
        active_ids = {t.track_id for t in tracks}
        dead_zone_ids = [
            tid for tid in list(self.active_zone_tracks)
            if tid not in active_ids and (current_time - self.last_seen_in_zone.get(tid, 0.0)) >= 4.0
        ]
        for tid in dead_zone_ids:
            self.active_zone_tracks.remove(tid)
            self.loitering_alert_fired.pop(tid, None)
            self.last_seen_in_zone.pop(tid, None)

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
        last_alert = self.last_alert_times.get(hash(dedup_key), 0.0)

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

        self.last_alert_times[hash(dedup_key)] = current_time
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

