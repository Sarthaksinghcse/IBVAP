"""
IBVAP Backend — Database Initialiser
Creates all tables and applies idempotent schema migrations.
Starts with zero predefined/fake cameras (real source-management architecture).
"""
from database.database import engine, Base, SessionLocal
from models.models import Camera, Zone
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def _apply_schema_migrations():
    """
    Idempotent column migrations for existing databases.
    SQLite raises OperationalError('duplicate column name') if the column already
    exists — we catch and ignore it so this is safe on every startup.
    """
    migrations = [
        ("cameras",    "source_type",    "TEXT DEFAULT 'CCTV'"),
        ("cameras",    "stream_url",     "TEXT"),
        ("cameras",    "stream_type",    "TEXT DEFAULT 'RTSP'"),
        ("cameras",    "created_at",     "DATETIME"),
        ("detections", "frame_index",    "INTEGER"),
        ("detections", "video_time_sec", "REAL"),
        ("detections", "plate_text",     "TEXT"),
        ("detections", "plate_confidence","REAL"),
        ("detections", "plate_status",   "TEXT"),
        ("detections", "plate_bbox_x",   "REAL"),
        ("detections", "plate_bbox_y",   "REAL"),
        ("detections", "plate_bbox_w",   "REAL"),
        ("detections", "plate_bbox_h",   "REAL"),
        ("detections", "night_vision_applied", "BOOLEAN DEFAULT 0"),
        ("detections", "frame_luminance",      "REAL"),
        ("detections", "lighting_profile",     "TEXT"),
        ("alerts",     "video_id",       "TEXT"),
        ("alerts",     "confidence",     "REAL"),
        ("alerts",     "bbox_x",         "REAL"),
        ("alerts",     "bbox_y",         "REAL"),
        ("alerts",     "bbox_w",         "REAL"),
        ("alerts",     "bbox_h",         "REAL"),
    ]
    with engine.connect() as conn:
        for table, col, coltype in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
                conn.commit()
                logger.info(f"[DB] Migration: added {table}.{col} ({coltype})")
            except Exception:
                pass  # Column already present


def init_db():
    """Create tables and apply migrations with zero demo cameras."""
    logger.info("[DB] Initializing database schema…")
    Base.metadata.create_all(bind=engine)

    # Apply column migrations for existing databases
    _apply_schema_migrations()

    db = SessionLocal()
    try:
        # Clean up legacy demo seeded camera entries (BOP-01 to BOP-07, WEBCAM-01)
        legacy_demo_ids = ["BOP-01", "BOP-02", "BOP-03", "BOP-04", "BOP-05", "BOP-06", "BOP-07", "WEBCAM-01"]
        deleted_count = db.query(Camera).filter(Camera.id.in_(legacy_demo_ids), Camera.stream_url.is_(None)).delete(synchronize_session=False)
        if deleted_count > 0:
            logger.info(f"[DB] Purged {deleted_count} legacy demo camera templates for clean zero-startup.")
            # Also clean orphan zones for purged demo cameras
            db.query(Zone).filter(Zone.source_id.in_(legacy_demo_ids)).delete(synchronize_session=False)
            db.commit()

        count = db.query(Camera).count()
        logger.info(f"[DB] Database ready. Active registered cameras: {count}")
    except Exception as e:
        logger.error(f"[DB] Init error: {e}")
        db.rollback()
    finally:
        db.close()



