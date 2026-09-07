# IBVAP — Intelligent Border Video Analytics Platform
### SIH 2025 Prototype

> Real-time AI-powered surveillance, detection, and threat response platform for border security.

---

## Quick Start

### 1. Frontend (Web Portal)

```bash
cd frontend/web_portal
npm install
npm run dev
```

Opens at: **http://localhost:5173**

> **Mock mode is ON by default** — the app runs with simulated AI events, no backend needed.

---

### 2. Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: **http://localhost:8000/docs**

---

### 3. Mock AI Engine

```bash
cd ai_engine
python mock_ai.py
```

Simulates YOLO detection events through the real API.

---

### 4. Switch to Real Mode

In `frontend/web_portal/.env`:

```env
VITE_USE_MOCK=false
```

---

## Architecture

```
Video/CCTV Input
      ↓
Python AI Engine (ai_engine/)
      ↓  POST /api/detections + /api/alerts
FastAPI Backend (backend/) ← SQLite
      ↓
 ┌────────────────┬──────────────────────┐
 ↓                ↓                      ↓
Web Portal    Security Software      Database
(React)      (separate team)         (ibvap.db)
      ↓
WebSocket (/ws/alerts)
```

**Rule: FastAPI is the ONLY communication hub. Nothing talks across boundaries directly.**

---

## Project Structure

```
IBVAP/
├── frontend/web_portal/   — React + Vite + TS + Tailwind
├── backend/               — FastAPI + SQLite
├── ai_engine/             — Python AI pipeline (YOLO Phase 8)
│   ├── mock_ai.py         — Run this for demo/development
│   ├── pipeline.py        — Real pipeline entry point (Phase 8)
│   ├── detection/         — YOLOv8 detector stub
│   ├── tracking/          — DeepSORT tracker stub
│   └── intelligence/      — Threat engine stub
├── models/                — YOLO .pt weights (download separately)
├── storage/
│   ├── videos/            — Uploaded CCTV videos
│   └── snapshots/         — Alert evidence screenshots
└── ibvap.db               — SQLite database (auto-created)
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cameras` | List all cameras |
| GET | `/api/alerts` | List alerts (filterable) |
| POST | `/api/alerts` | Create alert (broadcasts via WS) |
| PATCH | `/api/alerts/{id}` | Update alert status |
| POST | `/api/detections` | Log detection event |
| GET | `/api/detections` | List detections |
| POST | `/api/videos/upload` | Upload CCTV video |
| GET | `/api/analytics` | Dashboard analytics |
| WS | `/ws/alerts` | Real-time alert stream |

---

## Alert Status Flow

```
NEW → ACKNOWLEDGED → UNDER_INVESTIGATION → RESOLVED
```

## Threat Levels

| Level | Color | Use |
|-------|-------|-----|
| CRITICAL | 🔴 Red | Immediate response required |
| HIGH | 🟠 Orange | Security team notified |
| MEDIUM | 🟡 Yellow | Monitor closely |
| LOW | 🟢 Green | Informational |
| NONE | ⚪ Grey | No threat |

---

## Development Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Done | Web Portal UI |
| 2 | ✅ Done | FastAPI Backend |
| 3 | ✅ Done | Frontend ↔ Backend connected |
| 4 | ✅ Done | Video upload |
| 5 | ✅ Done | Mock AI detection events |
| 6 | ✅ Done | WebSocket real-time alerts |
| 7 | ✅ Done | API contract for Security Software |
| 8 | 🔲 Next | Real YOLO AI integration |

---

## For the Security Software Team

Connect to the same backend:

- **Base URL**: `http://localhost:8000`
- **WebSocket**: `ws://localhost:8000/ws/alerts`
- **Key endpoints**: `GET /api/alerts`, `PATCH /api/alerts/{id}`, `GET /api/cameras`
- **Swagger UI**: `http://localhost:8000/docs`

All alert status changes (acknowledge, resolve) are immediately visible to the Web Portal because both use the same SQLite database.

---

*IBVAP — Intelligent Border Video Analytics Platform | SIH 2025*
