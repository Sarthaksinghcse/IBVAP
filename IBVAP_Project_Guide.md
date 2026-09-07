# IBVAP — Intelligent Border Video Analytics Platform

> **SIH 2025 Prototype** | Real-time AI-powered surveillance, detection, and threat response platform for border security.

---

## 1. Executive Summary

Border security forces deploy CCTV cameras at Border Out Posts (BOPs), check posts, and border roads for surveillance. However, conventional CCTV systems only record and stream video — they require continuous human observation, which is slow, fatigue-prone, and unreliable over long shifts and large networks of cameras.

**IBVAP (Intelligent Border Video Analytics Platform)** is a software-defined, AI-powered layer that sits on top of existing IP-based CCTV infrastructure — **no new cameras, no specialised FRS/ANPR hardware, no additional capital expenditure**. It ingests live or recorded video streams and performs real-time detection, tracking, zone-intrusion alerting, behavioural analysis, and multi-channel alerting, all exposed through a unified command-centre dashboard.

The MVP demonstrates a working, end-to-end pipeline:

```
Video In → AI Analysis → Real-Time Dashboard → Alert Out
```

---

## 2. Problem Statement

Advanced surveillance capabilities — facial recognition, automatic number plate recognition (ANPR), intrusion detection, and object tracking — typically require specialised hardware and proprietary solutions, making large-scale deployment costly and difficult, particularly in remote border areas.

### Core Gaps in the Current System

| Gap | Description |
|---|---|
| **No automated intelligence** | Cameras only record; detection depends entirely on a human watching a screen |
| **Operator fatigue** | Continuous manual monitoring across dozens of feeds leads to missed events |
| **Hardware dependency** | FRS, ANPR, and intrusion detection usually require expensive dedicated smart-camera hardware |
| **Slow response time** | Detection itself is slow, so response to actual threats is delayed |
| **No searchable history** | No structured, searchable record of past incidents for analysis or accountability |

---

## 3. Proposed Solution — IBVAP Overview

IBVAP is a software platform that ingests live video streams from standard IP-based CCTV cameras and performs real-time video analytics using computer vision and AI, **without requiring any specialised surveillance hardware**.

### Design Principles

| Principle | Description |
|---|---|
| **Software-defined** | Runs entirely as a software layer over existing camera infrastructure |
| **Cost-effective** | Eliminates dependency on expensive dedicated FRS/ANPR/smart-camera hardware |
| **Scalable** | Same pipeline can be replicated across additional cameras / BOPs |
| **Real-time** | Detection-to-alert latency is designed to be near-instantaneous |
| **Explainable** | Every alert is generated with a clear, human-readable reason, not a black-box score |

---

## 4. MVP Feature List — Build Status (Verified Against Codebase)

> [!NOTE]
> The statuses below have been **verified against the actual source code** in the repository, not just the original report. Several features marked "Planned" in the initial report have since been fully implemented.

### 4.1 Detection Layer

| # | Feature | Description | Status |
|---|---|---|---|
| 1 | **Human Detection & Tracking** | Detects people in the video feed and assigns each a persistent unique ID across frames via YOLOv8n + built-in tracker. | ✅ **Built** — [detector.py](file:///e:/IBVAP/ai_engine/detection/detector.py), [tracker.py](file:///e:/IBVAP/ai_engine/tracking/tracker.py) |
| 2 | **Vehicle Detection & Classification** | Detects and classifies cars, trucks, motorcycles, buses, and bicycles in the frame. | ✅ **Built** — COCO class mapping in [detector.py](file:///e:/IBVAP/ai_engine/detection/detector.py) (lines 13–19) |
| 3 | **Persistent Object Tracking** | Maintains consistent identity of a tracked object (Person #1, #2…) across frames using IoU + centroid-distance matching with YOLO-to-stable-ID remapping. | ✅ **Built** — [tracker.py](file:///e:/IBVAP/ai_engine/tracking/tracker.py) (IoU + centroid hybrid, not simple centroid-only) |

### 4.2 Intelligence Layer

| # | Feature | Description | Status |
|---|---|---|---|
| 4 | **Virtual Fence / Restricted Zone Intrusion** | A custom polygon zone is defined on the frame; entry into it instantly triggers a breach alert. Zones are persisted in DB and configurable per camera via the web UI. | ✅ **Built** — [threat_engine.py](file:///e:/IBVAP/ai_engine/intelligence/threat_engine.py) (Shapely point-in-polygon), [zones.py](file:///e:/IBVAP/backend/routes/zones.py) |
| 5 | **Suspicious Activity / Loitering Detection** | Flags a tracked person as suspicious if they remain in a zone beyond a configurable time threshold (default 15s prototype → 30s in production code). | ✅ **Built** — [threat_engine.py](file:///e:/IBVAP/ai_engine/intelligence/threat_engine.py) (lines 192–194) |
| 6 | **Threat-Correlation Engine** | Combines multiple weak signals (zone breach + loitering + low confidence + night-time) into one weighted threat score: `NONE` / `LOW` / `MEDIUM` / `HIGH` / `CRITICAL`, with a human-readable reason string. | ✅ **Built** — [threat_engine.py](file:///e:/IBVAP/ai_engine/intelligence/threat_engine.py) `correlate_threat()` (lines 89–156) |
| 7 | **False-Positive Filtering** | Automatically filters out animals and low-confidence detections before they become alerts; documented with evidence dict. | ✅ **Built** — [threat_engine.py](file:///e:/IBVAP/ai_engine/intelligence/threat_engine.py) (lines 117–122) |
| 8 | **Face Detection & Recognition (Watchlist)** | Matches detected faces against a pre-registered watchlist using YuNet (face detection) + SFace (128-D embedding, cosine similarity). Includes photo registration, embedding extraction, and live track-face evaluation with caching. | ✅ **Built** — [face_engine.py](file:///e:/IBVAP/ai_engine/intelligence/face_engine.py), [watchlist.py](file:///e:/IBVAP/backend/routes/watchlist.py), [Watchlist.tsx](file:///e:/IBVAP/frontend/web_portal/src/pages/Watchlist.tsx) |
| 9 | **ANPR — Automatic Number Plate Recognition** | Locates license plate region via morphological gradient analysis, runs CRNN ONNX OCR, applies multi-frame temporal consensus for accuracy. | ✅ **Built** — [anpr_engine.py](file:///e:/IBVAP/ai_engine/intelligence/anpr_engine.py), [anpr.py](file:///e:/IBVAP/backend/routes/anpr.py) |
| 10 | **Night-Time / Low-Light Movement Detection** | Basic brightness/contrast enhancement (CLAHE + histogram equalisation) applied before detection to improve low-light frame quality. | ⚠️ **Partially Built** — Night-time awareness exists in threat correlation (auto-escalates to CRITICAL at night). CLAHE is used in ANPR plate preprocessing. Dedicated pre-detection frame enhancement for the main pipeline is **not yet implemented**. |

### 4.3 Alert Layer

| # | Feature | Description | Status |
|---|---|---|---|
| 11 | **Real-Time Multi-Signal Alert Generation** | Generates an alert the moment a zone-breach, loitering, or watchlist match occurs. Alerts are persisted to DB and broadcast via WebSocket to all connected clients. | ✅ **Built** — [alerts.py](file:///e:/IBVAP/backend/routes/alerts.py), [manager.py](file:///e:/IBVAP/backend/websocket/manager.py) |
| 12 | **Voice Alert (Audio Notification)** | Speaks a critical alert aloud in real time using browser Web Speech API (`speechSynthesis`), with a cooldown to prevent repeat spam. | ✅ **Built** — [audio.ts](file:///e:/IBVAP/frontend/web_portal/src/utils/audio.ts), [useWebSocket.ts](file:///e:/IBVAP/frontend/web_portal/src/hooks/useWebSocket.ts) |
| 13 | **Alert Logging (Timestamp + Snapshot)** | Every alert is stored with camera ID, alert type, reason, threat level, bounding box, and time for later review. | ✅ **Built** — Alert model in [models.py](file:///e:/IBVAP/backend/models/models.py) (lines 89–112) |

### 4.4 Dashboard Layer

| # | Feature | Description | Status |
|---|---|---|---|
| 14 | **Live Analytics Dashboard** | Real-time counters for humans/vehicles detected, active alerts, threat breakdown charts, and event timeline. | ✅ **Built** — [Dashboard.tsx](file:///e:/IBVAP/frontend/web_portal/src/pages/Dashboard.tsx), [Analytics.tsx](file:///e:/IBVAP/frontend/web_portal/src/pages/Analytics.tsx) |
| 15 | **Multi-Camera Grid View** | Displays multiple camera feeds side by side in a dynamic grid. Supports RTSP, webcam, and phone camera sources. | ✅ **Built** — [MultiCameraGrid.tsx](file:///e:/IBVAP/frontend/web_portal/src/components/dashboard/MultiCameraGrid.tsx), [CCTVPanel.tsx](file:///e:/IBVAP/frontend/web_portal/src/components/dashboard/CCTVPanel.tsx) |
| 16 | **Map-Based Camera Visualisation** | Plots camera locations on a tactical sector map with radar-ring visualisation and active zone indicators. | ✅ **Built** — [MapPage.tsx](file:///e:/IBVAP/frontend/web_portal/src/pages/MapPage.tsx) (custom tactical map, not Folium) |
| 17 | **Alert History & Search** | Filter and search past alerts by camera, threat level, status, alert ID, and object ID with pagination. | ✅ **Built** — [AlertHistory.tsx](file:///e:/IBVAP/frontend/web_portal/src/pages/AlertHistory.tsx) |

### Build Status Summary

```
✅ Built:            15 / 17 features  (88%)
⚠️ Partially Built:   1 / 17 features  (night-time enhancement — awareness exists, dedicated frame preprocessing not yet added)
🔲 Not Started:       1 / 17 features  (none — all originally "planned" features have been built)
```

---

## 5. System Architecture

IBVAP follows a six-stage pipeline, from video ingestion to command-centre integration:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Stage 1: VIDEO SOURCES                                                   │
│          Existing IP CCTV cameras (RTSP / MJPEG / Webcam / MP4 upload)  │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Stage 2: INGESTION LAYER                                                 │
│          OpenCV VideoCapture — reads frame-by-frame from any source      │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Stage 3: AI ANALYTICS ENGINE (ai_engine/)                                │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────────────────────┐  │
│  │  YOLOv8n     │──▶│  Tracker     │──▶│  Threat Engine              │  │
│  │  Detector    │   │  (IoU +      │   │  ├─ Zone Intrusion (Shapely)│  │
│  │              │   │   Centroid)  │   │  ├─ Loitering Analysis      │  │
│  └──────────────┘   └──────────────┘   │  ├─ Threat Correlation      │  │
│                                         │  ├─ False-Positive Filter   │  │
│  ┌──────────────┐   ┌──────────────┐   │  ├─ Night-Time Escalation   │  │
│  │  Face Engine │   │  ANPR Engine │   │  ├─ Face Recognition        │  │
│  │  (YuNet +    │   │  (Morph +    │   │  └─ ANPR                    │  │
│  │   SFace)     │   │   CRNN OCR)  │   └─────────────────────────────┘  │
│  └──────────────┘   └──────────────┘                                     │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │  POST /api/detections + POST /api/alerts
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ Stage 4: FASTAPI BACKEND HUB (backend/)                                  │
│                                                                          │
│  REST API ← SQLAlchemy ORM → SQLite (ibvap.db)                          │
│  WebSocket Manager → Broadcast to ALL connected clients                  │
│  Static File Server → /storage (videos, snapshots, watchlist photos)     │
└──────────────────────┬───────────────────────────────────────────────────┘
                       │  WebSocket broadcast
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌─────────────┐  ┌──────────┐  ┌──────────┐
   │ Stage 5:    │  │ Stage 5: │  │ Stage 4: │
   │ Web Portal  │  │ Security │  │ Database │
   │ (React +    │  │ Software │  │ (ibvap   │
   │  Vite + TS  │  │ (3rd     │  │  .db)    │
   │  + Tailwind)│  │  party)  │  │          │
   └─────────────┘  └──────────┘  └──────────┘
          │
          ▼
   ┌─────────────┐
   │ Stage 6:    │
   │ C2 / GIS    │
   │ Integration │  ← Documented API contract (not yet integrated)
   └─────────────┘
```

> [!IMPORTANT]
> **FastAPI is the ONLY communication hub.** No component talks to another directly. The AI Engine posts events to the backend; clients consume them via REST + WebSocket.

### Stage Implementation Status

| Stage | Component | Status |
|---|---|---|
| 1. Video Sources | RTSP, MJPEG, Webcam, MP4 upload | ✅ Implemented |
| 2. Ingestion Layer | OpenCV frame-by-frame read | ✅ Implemented |
| 3. AI Analytics Engine | Detection, tracking, behaviour, threat correlation | ✅ Implemented |
| 4. Data & Storage | SQLite + SQLAlchemy ORM, alert log, metadata | ✅ Implemented |
| 5. Application Layer | React web dashboard, WebSocket alerts, voice alerts | ✅ Implemented |
| 6. C2 Integration | External command & control interface | 📋 API contract documented, not live-integrated |

---

## 6. Technology Stack (Actual Implementation)

> [!NOTE]
> The original report referenced some technologies (Streamlit, dlib `face_recognition`, EasyOCR, pyttsx3, Folium) that have been **replaced with better alternatives** in the actual implementation. The table below reflects **what is actually used in the codebase**.

### AI Engine

| Layer | Report Planned | Actually Used | Purpose |
|---|---|---|---|
| Object Detection | YOLOv8 (Ultralytics) | ✅ **YOLOv8n** (Ultralytics) | Person / vehicle / animal detection |
| Object Tracking | Centroid-distance (MVP) | ✅ **IoU + Centroid Hybrid** | Persistent track IDs with YOLO-to-stable-ID remapping |
| Zone / Geometry | Shapely | ✅ **Shapely** | Point-in-polygon restricted zone check |
| Face Recognition | dlib `face_recognition` | ✅ **OpenCV YuNet + SFace** (ONNX) | 128-D face embedding, cosine similarity matching |
| ANPR / OCR | EasyOCR | ✅ **OpenCV CRNN ONNX** + morphological plate localisation | License plate text extraction |
| Voice Alerts | pyttsx3 (offline TTS) | ✅ **Web Speech API** (`speechSynthesis`) | Browser-based voice alerts (no Python dependency) |
| Video Processing | OpenCV | ✅ **OpenCV** | Frame extraction, bounding box overlay |
| Low-Light Enhancement | OpenCV histogram equalisation | ⚠️ **Partial** — CLAHE used in ANPR; night-time threat escalation exists; dedicated frame preprocessing not yet added |

### Backend

| Technology | Purpose |
|---|---|
| **FastAPI** | High-performance async Python web framework |
| **Uvicorn** | ASGI server |
| **SQLAlchemy 2** | ORM & database management |
| **SQLite** | Embedded database (zero-config, auto-created) |
| **Pydantic 2** | Request/response validation |
| **python-multipart** | File upload handling |
| **aiofiles** | Async file I/O |
| **websockets** | WebSocket protocol support |

### Frontend

| Report Planned | Actually Used | Purpose |
|---|---|---|
| Streamlit | ✅ **React 18 + Vite 5 + TypeScript** | Full SPA dashboard (far more capable than Streamlit) |
| CSV / SQLite client-side | ✅ **Axios + Zustand** | HTTP client + global state management |
| Folium (map) | ✅ **Custom tactical map component** | Sector map with radar rings, camera nodes |
| — | **Tailwind CSS 3** | Utility-first styling with dark/light themes |
| — | **Recharts** | Charts & visualisations |
| — | **Lucide React** | Icon system |
| — | **React Router 6** | Client-side routing (10 pages) |

---

## 7. Project Structure

```
IBVAP/
├── frontend/web_portal/            # React + Vite + TypeScript + Tailwind CSS
│   ├── src/
│   │   ├── App.tsx                     # Root app with React Router (10 routes)
│   │   ├── main.tsx                    # Entry point
│   │   ├── index.css                   # Global styles
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx               # Main overview: stats, charts, live feed
│   │   │   ├── LiveMonitoring.tsx           # Video upload + live feed + detection log
│   │   │   ├── Alerts.tsx                   # Active alerts with filtering & actions
│   │   │   ├── AlertHistory.tsx             # Historical alert log with search
│   │   │   ├── Cameras.tsx                  # Camera management (RTSP/Webcam/CCTV)
│   │   │   ├── Watchlist.tsx                # Face recognition watchlist CRUD
│   │   │   ├── MapPage.tsx                  # Tactical sector map
│   │   │   ├── Analytics.tsx                # Charts & aggregate analytics
│   │   │   ├── SystemStatus.tsx             # Backend/AI/WS health dashboard
│   │   │   └── Settings.tsx                 # AI thresholds, display preferences
│   │   ├── components/
│   │   │   ├── layout/                      # Sidebar, header, responsive shell
│   │   │   ├── dashboard/
│   │   │   │   ├── CCTVPanel.tsx                # Live feed with detection overlay
│   │   │   │   └── MultiCameraGrid.tsx          # Dynamic multi-camera grid view
│   │   │   ├── alerts/                      # Alert cards, filters, status badges
│   │   │   ├── cameras/                     # Camera cards, stream preview
│   │   │   ├── monitoring/                  # Upload panel, detection log
│   │   │   └── ui/                          # Shared buttons, modals, badges
│   │   ├── services/
│   │   │   ├── api.ts                       # Axios HTTP client
│   │   │   ├── websocket.ts                 # WebSocket singleton + auto-reconnect
│   │   │   └── mock/                        # Mock data generators (offline dev)
│   │   ├── store/
│   │   │   └── useStore.ts                  # Zustand global state
│   │   ├── hooks/                           # useWebSocket, useCameras, useAlerts
│   │   ├── types/
│   │   │   └── index.ts                     # All TypeScript interfaces & union types
│   │   └── utils/
│   │       └── audio.ts                     # Voice alert (Web Speech API)
│   ├── .env                             # VITE_USE_MOCK, VITE_API_URL, VITE_WS_URL
│   ├── package.json                     # React 18, Vite 5, Recharts, Zustand, Lucide
│   ├── tailwind.config.js               # Custom theme
│   └── vite.config.ts                   # Vite config
│
├── backend/                            # FastAPI + SQLAlchemy + SQLite
│   ├── main.py                              # App entry: CORS, static mounts, routers
│   ├── requirements.txt                     # Python dependencies
│   ├── database/
│   │   ├── database.py                      # SQLAlchemy engine + SessionLocal
│   │   └── init_db.py                       # Schema creation + migrations
│   ├── models/
│   │   └── models.py                        # 8 ORM models
│   ├── schemas/
│   │   └── schemas.py                       # Pydantic validation schemas
│   ├── routes/
│   │   ├── cameras.py                       # Camera CRUD + AI control
│   │   ├── videos.py                        # Video upload + AI analysis trigger
│   │   ├── detections.py                    # Detection event logging
│   │   ├── alerts.py                        # Alert CRUD + WS broadcast
│   │   ├── analytics.py                     # Aggregated analytics
│   │   ├── zones.py                         # Restricted zone polygon CRUD
│   │   ├── watchlist.py                     # Watchlist person + face embedding CRUD
│   │   └── anpr.py                          # ANPR event routes
│   ├── websocket/
│   │   └── manager.py                       # ConnectionManager + /ws/alerts
│   └── ibvap.db                             # SQLite database (auto-created)
│
├── ai_engine/                          # Python AI Pipeline
│   ├── mock_ai.py                           # Demo: simulated detection/alert loop
│   ├── pipeline.py                          # Real YOLOv8 surveillance pipeline
│   ├── detection/
│   │   └── detector.py                      # YOLOv8n inference + COCO class mapping
│   ├── tracking/
│   │   └── tracker.py                       # IoU + centroid hybrid tracker
│   └── intelligence/
│       ├── threat_engine.py                 # Zone intrusion, loitering, threat correlation
│       ├── face_engine.py                   # YuNet + SFace face recognition
│       └── anpr_engine.py                   # Morphological plate localisation + CRNN OCR
│
├── models/                             # AI model weights (download separately)
│   ├── yolov8n.pt                           # YOLOv8 nano weights
│   ├── face_detection_yunet_2023mar.onnx    # YuNet face detector
│   ├── face_recognition_sface_2021dec.onnx  # SFace face recogniser
│   └── text_recognition_CRNN_EN_2021sep.onnx # CRNN text recogniser for ANPR
│
├── storage/
│   ├── videos/                              # Uploaded CCTV videos
│   ├── snapshots/                           # Alert evidence screenshots
│   └── watchlist/                           # Watchlist face photos
│
├── venv/                               # Python virtual environment
└── README.md
```

---

## 8. Database Schema

### 8 ORM Models ([models.py](file:///e:/IBVAP/backend/models/models.py))

| Model | Table | Key Fields | Purpose |
|---|---|---|---|
| **Camera** | `cameras` | `name`, `source_type`, `stream_url`, `stream_type`, `status`, `ai_status`, `fps`, `resolution` | Camera registry |
| **Video** | `videos` | `filename`, `camera_id`, `status`, `file_path`, `file_size`, `duration` | Uploaded video files |
| **Detection** | `detections` | `camera_id`, `object_type`, `confidence`, `event_type`, `bbox`, `is_in_restricted_zone`, `loitering_duration`, `frame_index` | Every AI detection event |
| **Alert** | `alerts` | `alert_id`, `camera_id`, `threat_level`, `status`, `reason`, `snapshot_path`, `confidence`, `bbox` | Threat alerts with lifecycle |
| **Zone** | `zones` | `source_id`, `coordinates_json`, `zone_type`, `enabled` | Restricted zone polygons |
| **WatchlistPerson** | `watchlist_persons` | `name`, `identifier`, `threat_priority`, `photo_path`, `is_active` | Persons of interest |
| **FaceEmbedding** | `face_embeddings` | `person_id`, `embedding_json` | 128-D SFace feature vectors |
| **FaceRecognitionEvent** | `face_recognition_events` | `person_id`, `camera_id`, `similarity`, `cosine_score`, `event_type` | Face match events |
| **ANPREvent** | `anpr_events` | `vehicle_track_id`, `plate_text`, `plate_confidence`, `plate_status`, `vehicle_type` | Number plate readings |

---

## 9. API Reference

### REST Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check — service info |
| `GET` | `/health` | `{"status": "ok"}` |
| **Cameras** | | |
| `GET` | `/api/cameras` | List all registered cameras |
| `POST` | `/api/cameras` | Register a new camera |
| `PATCH` | `/api/cameras/{id}` | Update camera config |
| `DELETE` | `/api/cameras/{id}` | Remove camera + cascade delete |
| **Videos** | | |
| `POST` | `/api/videos/upload` | Upload MP4 for AI analysis |
| `GET` | `/api/videos` | List uploaded videos |
| **Detections** | | |
| `POST` | `/api/detections` | Log detection event (from AI engine) |
| `GET` | `/api/detections` | Query detections (filterable) |
| **Alerts** | | |
| `GET` | `/api/alerts` | List alerts (filter: status, threat_level, camera_id, video_id) |
| `GET` | `/api/alerts/{id}` | Get single alert |
| `POST` | `/api/alerts` | Create alert → **WebSocket broadcast** |
| `PATCH` | `/api/alerts/{id}` | Update status → **WebSocket broadcast** |
| **Zones** | | |
| `GET` | `/api/zones` | List zones |
| `POST` | `/api/zones` | Create restricted zone polygon |
| `PUT` | `/api/zones/{id}` | Update zone |
| `DELETE` | `/api/zones/{id}` | Delete zone |
| **Watchlist** | | |
| `GET` | `/api/watchlist` | List watchlist persons |
| `POST` | `/api/watchlist` | Add person with photo + face embedding |
| `DELETE` | `/api/watchlist/{id}` | Remove person |
| **ANPR** | | |
| `GET` | `/api/anpr/events` | List ANPR events |
| `GET` | `/api/anpr/stats` | ANPR statistics |
| **Analytics** | | |
| `GET` | `/api/analytics` | Aggregated dashboard statistics |

### WebSocket Protocol

**Endpoint:** `ws://localhost:8000/ws/alerts`

| Message Type | Direction | Payload | Trigger |
|---|---|---|---|
| `SYSTEM` | Server → Client | `{message, status}` | On connection |
| `ALERT` | Server → Client | Full alert object | New alert created |
| `ALERT_UPDATE` | Server → Client | `{id, status}` | Alert status changed |
| `DETECTION` | Server → Client | Detection data | New detection logged |
| `VIDEO_PROGRESS` | Server → Client | Progress info | Video processing update |
| `VIDEO_STATUS` | Server → Client | Status info | Video status change |
| `ping` / `pong` | Bidirectional | Plain text | Keep-alive (every 25s) |

---

## 10. Alert Lifecycle & Threat Levels

### Alert Status Flow

```
┌──────────┐       ┌──────────────┐       ┌───────────────────────┐       ┌──────────┐
│   NEW    │──────▶│ ACKNOWLEDGED │──────▶│ UNDER_INVESTIGATION   │──────▶│ RESOLVED │
└──────────┘       └──────────────┘       └───────────────────────┘       └──────────┘
  AI Engine          Operator              Investigation                   Threat
  creates            acknowledges          begins                         resolved
```

### Threat Level Classification (Threat-Correlation Engine)

| Level | Color | Trigger Conditions |
|---|---|---|
| 🔴 **CRITICAL** | Red | Zone intrusion + loitering past threshold, OR zone intrusion at night, OR critical watchlist match, OR vehicle in restricted zone |
| 🟠 **HIGH** | Orange | Zone intrusion (daytime), OR loitering detected, OR high-priority watchlist match |
| 🟡 **MEDIUM** | Yellow | Unidentified vehicle in monitored area, OR medium-priority watchlist match |
| 🟢 **LOW** | Green | Informational person or low-priority watchlist detection |
| ⚪ **NONE** | Grey | Filtered (animal or low-confidence) — never reaches alert |

---

## 11. Unique Differentiators

| Differentiator | Description | Implementation |
|---|---|---|
| **Threat-Correlation Engine** | Instead of raising a separate alert per signal, combines zone-breach, loitering, confidence, and time-of-day into a single explainable threat score with stated reason — reducing alert fatigue. | [threat_engine.py](file:///e:/IBVAP/ai_engine/intelligence/threat_engine.py) `correlate_threat()` |
| **False-Positive Filtering with Transparency** | Animals and low-confidence detections are filtered before they become an alert. Evidence dict documents what was filtered and why. | [threat_engine.py](file:///e:/IBVAP/ai_engine/intelligence/threat_engine.py) lines 117–122 |
| **Multi-Modal Alerting** | Critical threats are announced via voice (Web Speech API) in addition to the visual dashboard, so an operator doesn't need to be watching the screen at the moment of a breach. | [audio.ts](file:///e:/IBVAP/frontend/web_portal/src/utils/audio.ts), [useWebSocket.ts](file:///e:/IBVAP/frontend/web_portal/src/hooks/useWebSocket.ts) |
| **Zero New Hardware** | The entire platform runs as a software layer over cameras that are already deployed — directly addressing the cost and deployment-difficulty gap. | Architecture design |

---

## 12. Setup & Run Guide

### Prerequisites

| Requirement | Version |
|---|---|
| **Python** | 3.10+ |
| **Node.js** | ≥ 18.x |
| **npm** | ≥ 9.x |

### Step 1 — Backend (FastAPI)

```bash
cd backend

# Activate virtual environment
..\venv\Scripts\activate       # Windows
# source ../venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

> SQLite database `ibvap.db` is **auto-created** on first startup. Schema migrations are idempotent.

**Verify:** [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

### Step 2 — Frontend (React Web Portal)

```bash
cd frontend/web_portal
npm install
npm run dev
```

**Verify:** [http://localhost:5173](http://localhost:5173)

### Step 3 — Mock AI Engine (for demo, no GPU needed)

```bash
cd ai_engine
python mock_ai.py
```

Generates simulated detection + alert events every 6–18 seconds.

### Step 4 — Real AI Pipeline (requires YOLOv8 weights)

```bash
# Download model weights to models/ directory:
#   yolov8n.pt
#   face_detection_yunet_2023mar.onnx     (for face recognition)
#   face_recognition_sface_2021dec.onnx   (for face recognition)
#   text_recognition_CRNN_EN_2021sep.onnx (for ANPR)

python ai_engine/pipeline.py \
  --camera BOP-07 \
  --source path/to/video.mp4 \
  --model models/yolov8n.pt \
  --conf 0.40 \
  --loiter 15.0 \
  --fps 30 \
  --loop
```

### Environment Configuration

**Frontend** ([.env](file:///e:/IBVAP/frontend/web_portal/.env)):

| Variable | Default | Description |
|---|---|---|
| `VITE_USE_MOCK` | `false` | `true` = offline mock mode (no backend needed) |
| `VITE_API_URL` | `http://localhost:8000` | Backend REST API URL |
| `VITE_WS_URL` | `ws://localhost:8000/ws/alerts` | WebSocket endpoint |

---

## 13. Data Sources

No real border-surveillance footage is used or required. All data is either open-source/pretrained or self-generated:

| Data | Source | Notes |
|---|---|---|
| Detection model | YOLOv8n (COCO-pretrained, Ultralytics, open-source) | Recognises person, car, truck, motorcycle, animal out of the box |
| Demo footage | Self-recorded video simulating restricted-zone area | Exercises every feature in a single clip |
| Face data | Self-registered sample face images (team volunteers) | Demonstrates matching workflow only |
| Number plate data | Sample vehicle plates (own vehicles, with consent) | Validates OCR pipeline |
| Future fine-tuning | VIRAT, India Driving Dataset (IDD) — public research datasets | For Indian outdoor/border-like conditions |

---

## 14. Known Limitations

| Limitation | Details |
|---|---|
| **Night-time detection** | Currently uses night-time aware threat escalation only; no dedicated CLAHE/histogram frame preprocessing before YOLOv8 inference. Not a production-grade IR-camera pipeline. |
| **Face recognition accuracy** | Demonstrated on clear, close-range sample footage. Real deployment needs larger, higher-quality training data and better lighting. |
| **ANPR accuracy** | Works best on clearly visible, unobstructed plates at reasonable angles. Real-world conditions (motion blur, angled plates, dirt) require further tuning. |
| **Tracking** | Uses IoU + centroid-distance hybrid — more robust than simple centroid-only, but still not as robust as ByteTrack/DeepSORT under heavy occlusion and re-identification. |
| **Map visualisation** | Uses a custom tactical map component (not real GIS/satellite). Camera positions are computed relative to UI grid, not actual GPS coordinates. |
| **Single-machine deployment** | Currently runs all stages on one machine. No distributed/cloud deployment yet. |

---

## 15. Future Roadmap — Features to Build

> [!IMPORTANT]
> These features are **not yet built** in the codebase and represent the next development priorities.

### 🔲 High Priority (Near-Term)

| # | Feature | Description | Effort |
|---|---|---|---|
| F1 | **Night-Time / Low-Light Frame Enhancement** | Apply CLAHE + histogram equalisation to each frame **before** YOLOv8 inference in the main pipeline. Currently only used in ANPR plate preprocessing. Should be toggleable based on ambient brightness estimation. | Medium |
| F2 | **ByteTrack / DeepSORT Tracker Upgrade** | Replace the current IoU + centroid-distance tracker with ByteTrack or DeepSORT for robust multi-object tracking under heavy occlusion, re-identification after temporary disappearance, and appearance-based matching. | Medium |
| F3 | **Real GIS / Satellite Map Integration** | Replace the custom tactical sector map with a real mapping library (Leaflet / Mapbox) using actual GPS coordinates for camera placement, real satellite imagery, and geofence polygon overlays. | Medium |
| F4 | **Alert Snapshot Auto-Capture** | Automatically capture and save a frame snapshot when a HIGH/CRITICAL alert fires, linking it to the alert's `snapshot_path` field for forensic review. Currently the field exists in DB but is not auto-populated. | Small |

### 🔲 Medium Priority (Post-Hackathon)

| # | Feature | Description | Effort |
|---|---|---|---|
| F5 | **Command & Control (C2) System Integration** | Implement the documented Stage 6 API integration with real BOP C2 systems and GIS/mapping platforms. Currently represented as a documented API contract only. | Large |
| F6 | **Edge-Device Deployment** | Package the AI pipeline for deployment on Jetson-class edge hardware for true on-site, low-connectivity operation. Requires model optimisation (TensorRT) and lightweight deployment packaging. | Large |
| F7 | **Multi-Camera Sensor Fusion** | Build a unified threat map across an entire BOP sector by correlating detections from multiple cameras. Track a single person across camera handoffs. | Large |
| F8 | **Predictive Patrol-Route Suggestions** | Analyse historical alert patterns (time-of-day, location heatmaps) to suggest optimal patrol routes and shift schedules. | Large |
| F9 | **Production-Grade IR Pipeline** | Integrate with IR/thermal camera feeds and apply proper infrared-aware detection models for true night surveillance beyond CLAHE enhancement. | Large |

### 🔲 Lower Priority (Future Scope)

| # | Feature | Description | Effort |
|---|---|---|---|
| F10 | **Custom Model Fine-Tuning** | Fine-tune YOLOv8 on border-specific datasets (VIRAT, IDD) for improved accuracy on Indian terrain, clothing, and vehicle types. | Medium |
| F11 | **Multi-Language Voice Alerts** | Support Hindi and regional language TTS for voice alerts (currently English only via Web Speech API). | Small |
| F12 | **Role-Based Access Control (RBAC)** | Implement authentication and role-based permissions (admin, operator, viewer) for the web portal. | Medium |
| F13 | **Cloud Deployment & Horizontal Scaling** | Migrate from single-machine SQLite to PostgreSQL + Redis + container orchestration for multi-BOP deployment. | Large |
| F14 | **Mobile Companion App** | Build a lightweight mobile app (React Native) for field personnel to receive push notifications and view alert details. | Large |
| F15 | **Automated Report Generation** | Generate daily/weekly PDF incident reports with charts, alert summaries, and statistical analysis for command review. | Medium |
| F16 | **Anomaly Detection (Unsupervised)** | Use trajectory analysis and behavioral patterns to detect anomalous movement that doesn't fit predefined rules — moving beyond zone-based detection. | Large |

---

## 16. Expected Impact & Use Cases

| Use Case | Impact |
|---|---|
| **Border Intrusion Detection** | Detects and alerts on illegal movement across border fences or restricted zones without continuous human observation |
| **Vehicle Monitoring** | Identifies, tracks, classifies vehicles, and reads number plates automatically for checkpoint logging |
| **Watchlist / Face Recognition** | Matches detected faces against a watchlist and alerts security personnel in real time |
| **Night Surveillance** | Night-time aware threat escalation extends effective monitoring hours (full frame enhancement planned) |
| **Faster Response** | Real-time multi-channel alerts (dashboard + voice) allow personnel to act within seconds instead of minutes |
| **Reduced Cost** | Reuses existing IP CCTV infrastructure, avoiding capital expense of dedicated FRS/ANPR hardware |
| **Accountability** | Structured, searchable alert history with timestamps, reasons, and evidence for review and audit |

---

## 17. Key Files Quick Reference

| File | Purpose |
|---|---|
| [main.py](file:///e:/IBVAP/backend/main.py) | Backend entry point — CORS, routers, static mounts |
| [models.py](file:///e:/IBVAP/backend/models/models.py) | All 8+ SQLAlchemy ORM models |
| [schemas.py](file:///e:/IBVAP/backend/schemas/schemas.py) | Pydantic validation schemas |
| [alerts.py](file:///e:/IBVAP/backend/routes/alerts.py) | Alert CRUD + WebSocket broadcast |
| [manager.py](file:///e:/IBVAP/backend/websocket/manager.py) | WebSocket connection manager |
| [App.tsx](file:///e:/IBVAP/frontend/web_portal/src/App.tsx) | Frontend root with all 10 routes |
| [useStore.ts](file:///e:/IBVAP/frontend/web_portal/src/store/useStore.ts) | Zustand global state store |
| [api.ts](file:///e:/IBVAP/frontend/web_portal/src/services/api.ts) | Axios API client |
| [websocket.ts](file:///e:/IBVAP/frontend/web_portal/src/services/websocket.ts) | WebSocket singleton service |
| [audio.ts](file:///e:/IBVAP/frontend/web_portal/src/utils/audio.ts) | Voice alert (Web Speech API) |
| [pipeline.py](file:///e:/IBVAP/ai_engine/pipeline.py) | Real YOLOv8 surveillance pipeline |
| [mock_ai.py](file:///e:/IBVAP/ai_engine/mock_ai.py) | Demo mock AI event generator |
| [detector.py](file:///e:/IBVAP/ai_engine/detection/detector.py) | YOLOv8 inference wrapper |
| [tracker.py](file:///e:/IBVAP/ai_engine/tracking/tracker.py) | IoU + centroid hybrid tracker |
| [threat_engine.py](file:///e:/IBVAP/ai_engine/intelligence/threat_engine.py) | Threat correlation + zone + loitering |
| [face_engine.py](file:///e:/IBVAP/ai_engine/intelligence/face_engine.py) | YuNet + SFace face recognition |
| [anpr_engine.py](file:///e:/IBVAP/ai_engine/intelligence/anpr_engine.py) | License plate recognition |

---

*IBVAP — Intelligent Border Video Analytics Platform | SIH 2025*
