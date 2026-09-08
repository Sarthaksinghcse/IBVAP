# IBVAP Behaviour Analysis Module — Audit & Integration Report (Phase B1)

## Overview
This document records the architectural findings and integration points audited from `ai_engine/pipeline.py`, `ai_engine/intelligence/threat_engine.py`, `ai_engine/tracking/tracker.py`, `backend/routes/alerts.py`, and `backend/schemas/schemas.py`.

---

## Audit Summary Table

| Item | Findings & Specification |
|---|---|
| **Tracker Output** | `TrackedObject` instance containing: `track_id` (int), `object_type` ("PERSON"\|"VEHICLE"\|"ANIMAL"), `object_label` (e.g., "Person #1"), `bbox` (`{"x", "y", "w", "h"}` in 0–100%), `confidence` (0–100), `first_seen` (timestamp), `last_seen` (timestamp), `frame_count` (int), `in_zone` (bool), `zone_name` (str), `zone_entry_time` (float), `trajectory` (`List[Tuple[float, float]]` bottom_center points). Properties: `dwell_time`, `zone_dwell_time`, `bottom_center`, `center`. |
| **Frame Loop Integration Point** | Main processing loop in `ai_engine/pipeline.py` (lines 145–151), `backend/routes/videos.py` (lines 200–215), and `backend/routes/cameras.py` (lines 280–380). The per-frame behaviour hook attaches immediately after `active_tracks = self.tracker.update(detections)` and can be called from `ThreatEngine.process_tracks()` or directly by the pipeline runner. |
| **Alert Schema** | Fields required by `AlertCreate` / `Alert` ORM model:<br>• `camera_id`: `str`<br>• `video_id`: `Optional[str]`<br>• `event_type`: `str` (`ZONE_INTRUSION`, `LOITERING`, `DIRECTION_VIOLATION`, `SPEED_ANOMALY`, `GROUP_FORMATION`, `NIGHT_MOVEMENT`, `BEHAVIOUR_ANOMALY`)<br>• `object_type`: `str` (`PERSON`, `VEHICLE`, etc.)<br>• `object_id`: `str`<br>• `threat_level`: `ThreatLevel` enum (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`)<br>• `reason`: `str` (**mandatory human-readable reason & evidence**)<br>• `confidence`: `Optional[float]`<br>• `bbox`: `Optional[BBoxSchema]` (`{"x", "y", "w", "h"}`)<br>• `snapshot_path`: `Optional[str]` |
| **Alert Emit Call** | Direct in-process callback: `create_and_broadcast_alert_sync(data_dict: dict) -> dict` in `backend/routes/alerts.py` or HTTP POST via `ThreatEngine.post_alert(alert_data: dict) -> bool` to `POST /api/alerts/`. |
| **Zone Support** | Per-camera / per-video polygon zones are stored in the database (`zones` table via `backend/routes/zones.py`) using relative 0–100% polygon coordinates `[[x, y], ...]`. Fallback default polygons can be defined per-camera in `behaviour.yaml`. |
| **Config Mechanism** | Modular YAML config at `ai_engine/intelligence/behaviour/config/behaviour.yaml` supporting global defaults and per-camera overrides. |
| **Frame Budget Baseline** | Baseline YOLOv8n + Tracker CPU inference: ~46.7 ms/frame (~21.4 FPS). Added per-frame budget for behaviour analysis module: **≤ 9.3 ms/frame** (≤ 20% budget constraint). |

---

## Detailed Integration Hooks

### 1. Tracker Output Contract
The tracker emits a list of `TrackedObject` instances:
```python
class TrackedObject:
    track_id: int
    object_type: str       # PERSON, VEHICLE, ANIMAL
    object_label: str      # e.g., "Person #1"
    bbox: dict             # {"x": float, "y": float, "w": float, "h": float} in %
    confidence: float      # 0.0 to 100.0
    first_seen: float      # epoch timestamp
    last_seen: float       # epoch timestamp
    frame_count: int
    bottom_center: tuple   # (bx%, by%)
    center: tuple          # (cx%, cy%)
```

### 2. Alert Emission Hook
To trigger an alert that persists to SQLite DB and broadcasts to WebSockets:
```python
from backend.routes.alerts import create_and_broadcast_alert_sync

alert_payload = {
    "camera_id": camera_id,
    "video_id": video_id,
    "event_type": "ZONE_INTRUSION",
    "object_type": "PERSON",
    "object_id": "Person #1",
    "threat_level": "HIGH",
    "reason": "Person entered restricted zone 'Perimeter Alpha'",
    "confidence": 88.5,
    "bbox": {"x": 10.0, "y": 20.0, "w": 5.0, "h": 12.0},
    "snapshot_path": "storage/snapshots/behaviour/BOP-07_1_1725789000.jpg"
}
create_and_broadcast_alert_sync(alert_payload)
```

---

## Next Steps (Phase B2)
1. Check `scipy` dependency.
2. Build `TrackState` rolling window kinematic manager.
3. Build `zones.py` polygon helper with point-in-polygon logic.
4. Build `BehaviourEngine` public interface with `IBVAP_BEHAVIOUR_ENABLED` environment flag.
