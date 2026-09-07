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

from database.init_db import init_db
from routes import cameras, detections, alerts, videos, analytics, zones, watchlist, anpr
from websocket.manager import router as ws_router


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
    init_db()
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
    allow_origins     = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ─── Static Files (uploaded videos + snapshots + watchlist photos) ───────────

STORAGE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")
os.makedirs(os.path.join(STORAGE_ROOT, "videos"),    exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "snapshots"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_ROOT, "watchlist"), exist_ok=True)

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
def health():
    return {"status": "ok"}
