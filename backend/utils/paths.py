import os
import uuid
from fastapi import HTTPException

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}

def assert_within(path: str, root: str) -> str:
    """Ensure path is within root to prevent directory traversal attacks."""
    abs_root = os.path.abspath(root)
    abs_path = os.path.abspath(path)
    norm_root = os.path.normcase(abs_root)
    norm_path = os.path.normcase(abs_path)
    try:
        if os.path.commonpath([norm_path, norm_root]) != norm_root:
            raise HTTPException(status_code=400, detail=f"Path traversal detected! Path {abs_path} is outside of {abs_root}")
    except ValueError:
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
