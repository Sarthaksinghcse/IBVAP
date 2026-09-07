# IBVAP Backend API Contract
### Intelligent Border Video Analytics Platform — Integration Guide for Security Personnel Software

---

## 1. System Architecture Overview

The FastAPI backend serves as the **central and sole communication hub** for the entire IBVAP platform:

```
                    AI ENGINE (Python / YOLO)
                               ↓
                        FastAPI Backend
                        (Port 8000 / SQLite)
                       ↙                   ↘
       WEB PORTAL (React / Vite)    SECURITY PERSONNEL SOFTWARE (Desktop/Mobile)
```

### Strict Architectural Principles:
1. **Zero Direct Coupling**: The Web Portal and Security Software **NEVER** communicate directly.
2. **Single Source of Truth**: All alerts, cameras, detections, and statuses are persisted in the centralized SQLite database.
3. **Synchronized State**: Any status update performed by Security Personnel (e.g. Acknowledging an alert) is broadcasted via WebSocket in real-time to all connected Web Portals and other Security consoles without requiring a page refresh.

---

## 2. Server Connection Details

- **Base REST URL**: `http://localhost:8000`
- **Swagger Interactive Documentation**: `http://localhost:8000/docs`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`
- **WebSocket Alerts Endpoint**: `ws://localhost:8000/ws/alerts`
- **Static Storage Root (Snapshots/Videos)**: `http://localhost:8000/storage/`

---

## 3. Real-Time WebSocket Interface (`/ws/alerts`)

Security Personnel Software connects to `ws://localhost:8000/ws/alerts` to receive immediate push notifications when threats are identified by the AI Engine or when other operators update an alert's status.

### Protocol Flow:
1. **Connect**: Client opens standard WebSocket to `ws://localhost:8000/ws/alerts`.
2. **Initial Handshake Message**:
   ```json
   {
     "type": "SYSTEM",
     "data": {
       "message": "Connected to IBVAP WebSocket",
       "status": "ok"
     },
     "timestamp": "2026-08-24T12:00:00.000000"
   }
   ```
3. **Heartbeat / Keepalive**: Send string `"ping"` every 25 seconds; the server responds with `"pong"`.
4. **Incoming Alert Event (Push)**:
   ```json
   {
     "type": "ALERT",
     "data": {
       "id": "673f8d9b-4e1a-4d2c-9a1b-3f0e1a2b3c4d",
       "alert_id": "ALERT-20260824-A1B2C3D4",
       "camera_id": "BOP-07",
       "event_type": "ZONE_INTRUSION",
       "object_type": "PERSON",
       "object_id": "Person #14",
       "threat_level": "CRITICAL",
       "reason": "Person #14 entered Restricted Zone A and stayed for 32s. Confidence: 96.4%.",
       "status": "NEW",
       "snapshot_path": "/storage/snapshots/alert_673f8d9b.jpg",
       "created_at": "2026-08-24T12:05:30.000000",
       "updated_at": "2026-08-24T12:05:30.000000"
     },
     "timestamp": "2026-08-24T12:05:30.000000"
   }
   ```
5. **Incoming Alert Status Update (Push)**:
   ```json
   {
     "type": "ALERT_UPDATE",
     "data": {
       "id": "673f8d9b-4e1a-4d2c-9a1b-3f0e1a2b3c4d",
       "status": "ACKNOWLEDGED"
     },
     "timestamp": "2026-08-24T12:06:15.000000"
   }
   ```

---

## 4. REST API Endpoints Specification

### 4.1 Alerts API

#### **GET `/api/alerts/`**
Retrieve alerts with optional filtering.

- **Query Parameters**:
  - `status` (*optional, string*): `NEW` | `ACKNOWLEDGED` | `UNDER_INVESTIGATION` | `RESOLVED`
  - `threat_level` (*optional, string*): `CRITICAL` | `HIGH` | `MEDIUM` | `LOW` | `NONE`
  - `camera_id` (*optional, string*): e.g. `BOP-07`
  - `limit` (*optional, integer*): Default `100`

- **Response `200 OK`**:
  ```json
  [
    {
      "id": "673f8d9b-4e1a-4d2c-9a1b-3f0e1a2b3c4d",
      "alert_id": "ALERT-20260824-A1B2C3D4",
      "camera_id": "BOP-07",
      "event_type": "ZONE_INTRUSION",
      "object_type": "PERSON",
      "object_id": "Person #14",
      "threat_level": "CRITICAL",
      "reason": "Person entered Restricted Zone A...",
      "status": "NEW",
      "snapshot_path": "/storage/snapshots/alert_673f8d9b.jpg",
      "created_at": "2026-08-24T12:05:30",
      "updated_at": "2026-08-24T12:05:30"
    }
  ]
  ```

---

#### **GET `/api/alerts/{alert_id}`**
Retrieve complete details for a single alert.

- **Response `200 OK`**: Same object structure as above.
- **Response `404 Not Found`**: `{"detail": "Alert not found"}`

---

#### **POST `/api/alerts/`**
Generate a new alert. (Normally invoked by AI Engine / Threat Engine).

- **Request Body**:
  ```json
  {
    "camera_id": "BOP-07",
    "event_type": "ZONE_INTRUSION",
    "object_type": "PERSON",
    "object_id": "Person #14",
    "threat_level": "CRITICAL",
    "reason": "Person entered Restricted Zone A and remained for 32 seconds.",
    "snapshot_path": "/storage/snapshots/alert_sample.jpg"
  }
  ```
- **Response `200 OK`**: AlertResponse object with generated `id`, `alert_id`, and `created_at`.
- **Side Effect**: Broadcasts `ALERT` payload to all WebSocket clients automatically.

---

#### **PATCH `/api/alerts/{alert_id}`**
Update the operational status of an alert (Used by Security Personnel Software).

- **Request Body**:
  ```json
  {
    "status": "ACKNOWLEDGED"
  }
  ```
  *Allowed status values*:
  - `NEW` — Initial unhandled alert
  - `ACKNOWLEDGED` — Operator has seen and acknowledged the alert
  - `UNDER_INVESTIGATION` — Patrol dispatched or incident under active review
  - `RESOLVED` — Threat neutralized / cleared

- **Response `200 OK`**: Updated AlertResponse object.
- **Side Effect**: Broadcasts `ALERT_UPDATE` to all Web Portals and Security clients immediately.

---

### 4.2 Detections API

#### **GET `/api/detections/`**
Query real-time/historical object detections logged by the AI Engine.

- **Query Parameters**:
  - `camera_id` (*optional*): e.g. `BOP-07`
  - `limit` (*optional*): Default `100`

- **Response `200 OK`**:
  ```json
  [
    {
      "id": "det-12345",
      "camera_id": "BOP-07",
      "video_id": null,
      "object_type": "PERSON",
      "object_id": "Person #14",
      "confidence": 96.4,
      "zone": "Restricted Zone A",
      "event_type": "ZONE_INTRUSION",
      "bbox": {
        "x": 28.5,
        "y": 18.0,
        "w": 14.2,
        "h": 52.0
      },
      "is_in_restricted_zone": true,
      "loitering_duration": 32,
      "timestamp": "2026-08-24T12:05:28"
    }
  ]
  ```

---

### 4.3 Cameras API

#### **GET `/api/cameras/`**
List all deployed border observation posts (BOP cameras) and their operational status.

- **Response `200 OK`**:
  ```json
  [
    {
      "id": "BOP-01",
      "name": "BOP-01",
      "location": "Sector Alpha — Gate A",
      "status": "ONLINE",
      "ai_status": "RUNNING",
      "fps": 25.0,
      "resolution": "1920x1080",
      "last_activity": "2026-08-24T12:05:00"
    }
  ]
  ```

---

### 4.4 Analytics API

#### **GET `/api/analytics/`**
Aggregated statistics for security command center overviews.

- **Response `200 OK`**:
  ```json
  {
    "total_detections": 247,
    "total_alerts": 28,
    "people_count": 24,
    "vehicle_count": 11,
    "loitering_count": 5,
    "intrusion_count": 3,
    "cameras_online": 5,
    "cameras_total": 7,
    "ai_engine_fps": 24.8,
    "processing_time_ms": 42.0,
    "threat_breakdown": {
      "critical": 2,
      "high": 3,
      "medium": 4,
      "low": 9,
      "none": 10
    }
  }
  ```

---

### 4.5 Videos API

#### **POST `/api/videos/upload`**
Upload recorded surveillance footage for batch analysis.

- **Form Data**:
  - `file`: Multipart binary video file (`.mp4`, `.avi`, `.mkv`)
- **Response `200 OK`**:
  ```json
  {
    "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "filename": "perimeter_sector_alpha.mp4",
    "camera_id": null,
    "status": "PROCESSING",
    "file_path": "E:\\IBVAP\\storage\\videos\\9b1deb4d_perimeter_sector_alpha.mp4",
    "file_size": 24159190,
    "duration": null,
    "created_at": "2026-08-24T12:00:00"
  }
  ```

---

## 5. Threat Classification Matrix

| Threat Level | Color Reference | Criteria | Required Operator Response |
| :--- | :--- | :--- | :--- |
| **`CRITICAL`** | 🔴 Red | Verified restricted zone breach with loitering > 25s | Instant patrol dispatch; alarm sounded |
| **`HIGH`** | 🟠 Orange | Restricted zone breach or prolonged perimeter loitering | Radio patrol alert; live track target |
| **`MEDIUM`** | 🟡 Yellow | Unidentified vehicle or anomalous movement pattern | Security assessment; visual verification |
| **`LOW`** | 🟢 Green | Routine movement in exterior non-restricted sector | Automated logging; no action required |
| **`NONE`** | ⚪ Slate | Environmental noise or cleared detection | Informational log |

---

## 6. End-to-End Test Workflow

To verify your Security Software client with the live IBVAP server:

1. **Connect WebSocket**: Connect to `ws://localhost:8000/ws/alerts`
2. **Trigger Test Alert**:
   ```bash
   curl -X POST http://localhost:8000/api/alerts/ \
     -H "Content-Type: application/json" \
     -d '{
       "camera_id": "BOP-07",
       "event_type": "ZONE_INTRUSION",
       "object_type": "PERSON",
       "object_id": "Intruder #99",
       "threat_level": "CRITICAL",
       "reason": "Test intrusion triggered via integration contract."
     }'
   ```
3. **Verify Push**: Observe the `ALERT` message arriving over your open WebSocket connection within < 50ms.
4. **Acknowledge Alert**:
   ```bash
   curl -X PATCH http://localhost:8000/api/alerts/<ALERT_UUID> \
     -H "Content-Type: application/json" \
     -d '{"status": "ACKNOWLEDGED"}'
   ```
5. **Verify State Synchronization**: Both your software and the Web Portal UI will reflect `ACKNOWLEDGED` immediately.

---

## 7. Watchlist & Face Recognition Interface (`/api/watchlist`)

IBVAP integrates real OpenCV YuNet face detection and SFace 128-D embedding extraction.

### Endpoints:
* `GET /api/watchlist` — List all registered persons of interest.
* `POST /api/watchlist` — Form-data (`name`, `identifier`, `threat_priority`, `file`). Validates face presence, extracts 128-D embedding, and stores photo.
* `GET /api/watchlist/{id}` — Get single target profile.
* `PATCH /api/watchlist/{id}` — Update target metadata / active status.
* `DELETE /api/watchlist/{id}` — Remove target and embeddings.
* `POST /api/watchlist/test-match` — Submit probe photo for real face match evaluation against active watchlist.

---

## 8. ANPR Interface (`/api/anpr`)

IBVAP integrates real morphological plate localization and OpenCV CRNN ONNX text recognition.

### Endpoints:
* `GET /api/anpr/events` — Query recorded plate events. Filterable by `camera_id`, `plate_text`, `plate_status`, `limit`.
* `GET /api/anpr/stats` — Real-time plate statistics (total tracked, readable count, unreadable count, list of unique plates).
* `POST /api/anpr/test-recognize` — Submit vehicle image or plate crop for instant plate localization and neural OCR reading.


