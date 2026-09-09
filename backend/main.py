"""
IBVAP Backend — FastAPI Application Entry Point

Architecture:
  AI Engine  ──→  POST /api/detections
  AI Engine  ──→  POST /api/alerts   ──→  WebSocket broadcast ──→  Web Portal + Security Software
  Web Portal ──→  GET /api/*
  Sec. Software → GET/PATCH /api/alerts/*
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import sys
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.dirname(_backend_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from database.init_db import init_db
from routes import cameras, detections, alerts, videos, analytics, zones, watchlist, anpr, stream
from websocket.manager import router as ws_router, manager


import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ibvap")


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 55)
    logger.info("  IBVAP Backend Starting…")
    logger.info("=" * 55)
    import asyncio
    manager.set_loop(asyncio.get_running_loop())
    init_db()

    # Clean up stale video analysis jobs interrupted by server restart
    try:
        from database.database import SessionLocal
        from models.models import Video
        s = SessionLocal()
        stuck_vids = s.query(Video).filter(Video.status.in_(["PROCESSING", "AI_ANALYZING"])).all()
        for sv in stuck_vids:
            sv.status = "ERROR"
            logger.info(f"[Lifespan] Reset stale video analysis job {sv.id} to ERROR")
        s.commit()
        s.close()
    except Exception as se:
        logger.warning(f"[Lifespan] Failed checking stale video jobs: {se}")

    logger.info("  Backend ready. Docs: http://localhost:8000/docs")
    yield
    logger.info("  IBVAP Backend shutting down.")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "IBVAP API",
    description = "Intelligent Border Video Analytics Platform — Backend API\n\n"
                  "Connects: AI Engine | Web Portal | Security Personnel Software",
    version     = "1.0.0",
    lifespan    = lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
    allow_origins     = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://localhost",
        "http://localhost:8000",
        "file://",              # Electron production (loads from file://)
        "app://.",              # Electron custom protocol
    ],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ─── Static Files (uploaded videos + snapshots + watchlist photos) ───────────

from utils.paths import get_storage_root

STORAGE_ROOT = get_storage_root()
os.makedirs(os.path.join(STORAGE_ROOT, "videos"),    exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "snapshots"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "snapshots", "faces"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "watchlist"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "users"), exist_ok=True)

app.mount("/storage", StaticFiles(directory=STORAGE_ROOT), name="storage")

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(cameras.router,    prefix="/api/cameras",    tags=["Cameras"])
app.include_router(videos.router,     prefix="/api/videos",     tags=["Videos"])
app.include_router(detections.router, prefix="/api/detections", tags=["Detections"])
app.include_router(alerts.router,     prefix="/api/alerts",     tags=["Alerts"])
app.include_router(analytics.router,  prefix="/api/analytics",  tags=["Analytics"])
app.include_router(zones.router,      prefix="/api/zones",      tags=["Zones"])
app.include_router(watchlist.router,  prefix="/api/watchlist",  tags=["Watchlist"])
app.include_router(anpr.router,       tags=["ANPR"])
app.include_router(stream.router,     prefix="/api/stream",     tags=["stream"])
app.include_router(ws_router)



# ─── Health Endpoints ─────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {
        "service": "IBVAP Backend",
        "version": "1.0.0",
        "status":  "online",
        "docs":    "/docs",
    }

@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health():
    db_ok = False
    try:
        from database.database import SessionLocal
        from sqlalchemy import text
        s = SessionLocal()
        s.execute(text("SELECT 1"))
        s.close()
        db_ok = True
    except Exception:
        db_ok = False

    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "yolov8n.pt")
    yolo_ok = os.path.exists(model_path)

    tesseract_ok = os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

    return {
        "status": "healthy" if db_ok and yolo_ok else "degraded",
        "api": "online",
        "database": "connected" if db_ok else "error",
        "yolo_model": "ready" if yolo_ok else "missing",
        "tesseract_ocr": "installed" if tesseract_ok else "not_found",
        "active_ws_clients": len(manager.active_connections) if hasattr(manager, "active_connections") else 0,
    }
