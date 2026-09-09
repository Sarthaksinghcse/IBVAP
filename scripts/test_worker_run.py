import os, sys, traceback
sys.path.insert(0, os.path.abspath("backend"))
sys.path.insert(0, os.path.abspath("."))

from routes.videos import run_video_inference_worker, _video_jobs
from database.database import SessionLocal
from models.models import Video

db = SessionLocal()
v = db.query(Video).filter(Video.id == "5322ac9a-ece1-44ff-a9f5-9b5614f2dae7").first()
print("Video in DB:", v.id, v.status, v.file_path, os.path.exists(v.file_path))
db.close()

try:
    print("Starting worker for video...")
    run_video_inference_worker(v.id, v.file_path, v.camera_id)
    print("Worker finished! Job status:", _video_jobs.get(v.id))
except Exception as e:
    print("Worker exception:", e)
    traceback.print_exc()
