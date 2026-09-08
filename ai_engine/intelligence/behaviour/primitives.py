"""
Layer 1 Behaviour Primitives Module
===================================
Defines interpretable, zero-training behaviour rules corresponding to SIH PS requirements:
1. Virtual Fence / Zone Intrusion
2. Loitering Detection
3. Direction Violation (Wrong-Way Movement)
4. Speed Anomaly (Running & Sudden Sprinting)
5. Group Formation / Clustering
6. Night-Time Presence & Movement

Each primitive returns a tuple of: (fired: bool, reason: str, evidence: dict)
"""
import math
from datetime import datetime
from typing import List, Tuple, Dict, Optional, Set
from ai_engine.intelligence.behaviour.track_state import TrackState
from ai_engine.intelligence.behaviour.zones import ZoneDefinition


def check_zone_intrusion(
    track: TrackState,
    zones: List[ZoneDefinition],
    config: dict,
    timestamp: float
) -> Tuple[bool, str, dict]:
    """
    Primitive 1: Virtual Fence Intrusion
    Fires when a track enters a restricted zone and remains present for min_frames.
    """
    min_frames = config.get("min_frames", 3)
    if track.dwell_frames < min_frames:
        return False, "", {}

    bottom_pt = track.current_bottom_center
    for z in zones:
        if z.zone_type == "restricted" and z.contains_point(bottom_pt):
            reason = f"{track.object_type.title()} #{track.track_id} entered restricted zone '{z.name}'"
            evidence = {
                "primitive": "zone_intrusion",
                "track_id": track.track_id,
                "object_type": track.object_type,
                "zone_name": z.name,
                "dwell_frames": track.dwell_frames,
                "point": bottom_pt
            }
            return True, reason, evidence

    return False, "", {}


def check_loitering(
    track: TrackState,
    zones: List[ZoneDefinition],
    config: dict,
    timestamp: float
) -> Tuple[bool, str, dict]:
    """
    Primitive 2: Loitering Detection
    Fires when a track remains in a zone > loiter_seconds and net displacement is small.
    """
    loiter_seconds = config.get("loiter_seconds", 15.0)
    max_displacement = config.get("max_displacement_pct", 15.0)

    bottom_pt = track.current_bottom_center
    for z in zones:
        if z.contains_point(bottom_pt):
            dwell_s = track.zone_dwell_seconds(z.name, timestamp)
            if dwell_s >= loiter_seconds:
                disp = track.get_net_displacement_pct(window_seconds=loiter_seconds)
                if disp <= max_displacement:
                    reason = f"{track.object_type.title()} #{track.track_id} loitering in '{z.name}' for {dwell_s:.0f}s"
                    evidence = {
                        "primitive": "loitering",
                        "track_id": track.track_id,
                        "zone_name": z.name,
                        "dwell_seconds": round(dwell_s, 1),
                        "net_displacement_pct": round(disp, 1)
                    }
                    return True, reason, evidence

    return False, "", {}


def check_direction_violation(
    track: TrackState,
    zones: List[ZoneDefinition],
    config: dict,
    timestamp: float
) -> Tuple[bool, str, dict]:
    """
    Primitive 3: Direction Violation (Wrong-Way Movement)
    Fires when track movement direction opposes expected flow direction by > angular_threshold.
    """
    min_frames = config.get("min_frames", 5)
    angular_threshold = config.get("angular_threshold_deg", 120.0)

    if track.dwell_frames < min_frames or track.speed_pct_s < 0.5:
        return False, "", {}

    bottom_pt = track.current_bottom_center
    for z in zones:
        expected_deg = z.expected_flow_deg
        if expected_deg is not None and z.contains_point(bottom_pt):
            heading = track.direction_deg
            diff = abs(heading - expected_deg)
            if diff > 180.0:
                diff = 360.0 - diff

            if diff >= angular_threshold:
                reason = (
                    f"{track.object_type.title()} #{track.track_id} moving against expected flow in '{z.name}' "
                    f"(heading {heading:.0f}°, expected {expected_deg:.0f}°)"
                )
                evidence = {
                    "primitive": "direction_violation",
                    "track_id": track.track_id,
                    "zone_name": z.name,
                    "heading_deg": round(heading, 1),
                    "expected_deg": round(expected_deg, 1),
                    "angular_diff_deg": round(diff, 1)
                }
                return True, reason, evidence

    return False, "", {}


def check_speed_anomaly(
    track: TrackState,
    zones: List[ZoneDefinition],
    config: dict,
    timestamp: float
) -> Tuple[bool, str, dict]:
    """
    Primitive 4: Speed Anomaly (Running / Sudden Acceleration)
    Uses scale-invariant speed (bbox-heights/sec) to detect running or sprinting.
    """
    run_threshold = config.get("run_threshold_h_per_s", 1.5)
    sprint_delta = config.get("sprint_delta_h_per_s", 0.8)

    if track.dwell_frames < 3:
        return False, "", {}

    speed_h_s = track.speed_h_s
    accel = track.acceleration_h_s2

    if speed_h_s >= run_threshold:
        reason = f"{track.object_type.title()} #{track.track_id} running / fast movement (speed {speed_h_s:.1f} h/s)"
        evidence = {
            "primitive": "speed_anomaly",
            "track_id": track.track_id,
            "sub_type": "running",
            "speed_h_s": round(speed_h_s, 2),
            "threshold_h_s": run_threshold
        }
        return True, reason, evidence

    if accel >= sprint_delta and speed_h_s >= 0.8:
        reason = f"{track.object_type.title()} #{track.track_id} sudden acceleration burst (accel {accel:.1f} h/s²)"
        evidence = {
            "primitive": "speed_anomaly",
            "track_id": track.track_id,
            "sub_type": "acceleration_spike",
            "acceleration_h_s2": round(accel, 2),
            "speed_h_s": round(speed_h_s, 2)
        }
        return True, reason, evidence

    return False, "", {}


def check_group_formation(
    all_tracks: List[TrackState],
    zones: List[ZoneDefinition],
    config: dict,
    timestamp: float
) -> List[Tuple[bool, str, dict]]:
    """
    Primitive 5: Group Formation / Clustering
    Evaluates active person tracks to find clusters of size >= group_n within group_radius_pct.
    Returns list of fired alerts for detected groups.
    """
    group_n = config.get("group_n", 4)
    group_radius = config.get("group_radius_pct", 15.0)

    person_tracks = [t for t in all_tracks if t.object_type == "PERSON" and t.dwell_frames >= 3]
    if len(person_tracks) < group_n:
        return []

    alerts = []
    visited = set()

    for i, t1 in enumerate(person_tracks):
        if t1.track_id in visited:
            continue

        cluster = [t1]
        c1_x, c1_y = t1.current_centroid

        for j, t2 in enumerate(person_tracks):
            if i != j and t2.track_id not in visited:
                c2_x, c2_y = t2.current_centroid
                dist = math.hypot(c1_x - c2_x, c1_y - c2_y)
                if dist <= group_radius:
                    cluster.append(t2)

        if len(cluster) >= group_n:
            cluster_ids = [t.track_id for t in cluster]
            for t in cluster:
                visited.add(t.track_id)

            # Determine zone name if any
            zone_name = "surveillance sector"
            bottom_pt = t1.current_bottom_center
            for z in zones:
                if z.contains_point(bottom_pt):
                    zone_name = z.name
                    break

            reason = f"Group of {len(cluster)} persons formed in '{zone_name}'"
            evidence = {
                "primitive": "group_formation",
                "group_size": len(cluster),
                "track_ids": cluster_ids,
                "zone_name": zone_name,
                "radius_pct": group_radius
            }
            alerts.append((True, reason, evidence))

    return alerts


def check_night_presence(
    track: TrackState,
    night_hours_cfg: dict,
    config: dict,
    timestamp: float
) -> Tuple[bool, str, dict]:
    """
    Primitive 6: Night-Time Movement Detection
    Fires when motion/track is present during configured night hours.
    """
    min_frames = config.get("min_frames", 5)
    if track.dwell_frames < min_frames or track.speed_pct_s < 0.2:
        return False, "", {}

    start_hour = night_hours_cfg.get("start_hour", 19)
    end_hour = night_hours_cfg.get("end_hour", 6)

    dt = datetime.fromtimestamp(timestamp)
    hour = dt.hour

    # Evaluate overnight window (e.g. 19:00 to 06:00)
    is_night = (hour >= start_hour or hour < end_hour) if start_hour > end_hour else (start_hour <= hour < end_hour)

    if is_night:
        time_str = dt.strftime("%H:%M:%S")
        reason = f"{track.object_type.title()} #{track.track_id} movement detected during night hours ({time_str})"
        evidence = {
            "primitive": "night_presence",
            "track_id": track.track_id,
            "object_type": track.object_type,
            "time_str": time_str,
            "speed_pct_s": round(track.speed_pct_s, 2)
        }
        return True, reason, evidence

    return False, "", {}
