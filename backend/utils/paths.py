import os
import uuid
from fastapi import HTTPException

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}

def get_storage_root() -> str:
    """
    Returns the canonical persistent storage directory.
    Priority:
    1. IBVAP_STORAGE_ROOT environment variable
    2. Canonical project repository storage: C:\\Users\\thaku\\OneDrive\\Desktop\\IBVAP\\storage
    3. Sibling storage folder relative to backend
    """
    env_storage = os.environ.get("IBVAP_STORAGE_ROOT")
    if env_storage and os.path.isdir(env_storage):
        return os.path.abspath(env_storage)

    canonical_storage = r"C:\Users\thaku\OneDrive\Desktop\IBVAP\storage"
    if os.path.isdir(canonical_storage):
        return os.path.abspath(canonical_storage)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fallback = os.path.normpath(os.path.join(base_dir, "..", "storage"))
    os.makedirs(fallback, exist_ok=True)
    return os.path.abspath(fallback)


def get_db_path() -> str:
    """
    Returns the canonical persistent SQLite database path.
    Priority:
    1. IBVAP_DB_PATH environment variable
    2. Canonical project repository database: C:\\Users\\thaku\\OneDrive\\Desktop\\IBVAP\\backend\\ibvap.db
    3. Sibling ibvap.db relative to backend
    """
    env_db = os.environ.get("IBVAP_DB_PATH")
    if env_db and os.path.isabs(env_db):
        os.makedirs(os.path.dirname(env_db), exist_ok=True)
        return os.path.abspath(env_db)

    canonical_db = r"C:\Users\thaku\OneDrive\Desktop\IBVAP\backend\ibvap.db"
    if os.path.isfile(canonical_db):
        return os.path.abspath(canonical_db)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(os.path.join(base_dir, "ibvap.db"))

def assert_within(path: str, root: str) -> str:
    """Ensure path is within root to prevent directory traversal attacks."""
    abs_root = os.path.abspath(root)
    abs_path = os.path.abspath(path)
    norm_root = os.path.normcase(abs_root)
    norm_path = os.path.normcase(abs_path)
    try:
        if os.path.commonpath([norm_path, norm_root]) != norm_root:
            raise HTTPException(status_code=400, detail=f"Path traversal detected! Path {abs_path} is outside of {abs_root}")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail=f"Path traversal detected! Path {abs_path} is outside of {abs_root}")
    return abs_path

def extension_from_content_type(content_type: str) -> str:
    """Returns safe file extension from content-type."""
    if not content_type:
        return ".bin"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "bmp" in content_type:
        return ".bmp"
    if "mp4" in content_type:
        return ".mp4"
    if "avi" in content_type:
        return ".avi"
    return ".bin"

def safe_filename(person_id: str, ext: str) -> str:
    """Generates a safe filename entirely server-side."""
    safe_ext = ext if ext in ALLOWED_IMAGE_EXTENSIONS else ".bin"
    return f"{str(person_id)[:8]}_{uuid.uuid4().hex[:8]}{safe_ext}"

def safe_video_filename(video_id: str, ext: str) -> str:
    """Generates a safe video filename entirely server-side."""
    safe_ext = ext if ext in ALLOWED_VIDEO_EXTENSIONS else ".bin"
    return f"{str(video_id)}_{uuid.uuid4().hex[:8]}{safe_ext}"
