from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# ─── Database Path ────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, "ibvap.db")

DATABASE_URL = f"sqlite:///{DB_PATH}"

# ─── Engine + Session ─────────────────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    # Phase 1.5 (I2): Add busy timeout to prevent "database is locked" during
    # concurrent access from video worker threads and FastAPI request threads.
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)

# Phase 1.5 (I2): Enable WAL journal mode on every new connection.
# WAL allows concurrent readers + one writer without blocking, preventing
# the "database is locked" error when a long-running video job holds the DB.
@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ─── Dependency ───────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
