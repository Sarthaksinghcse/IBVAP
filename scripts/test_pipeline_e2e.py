import cv2, os, sys, time
sys.path.insert(0, 'backend')
sys.path.insert(0, '.')

from ai_engine.detection.detector import Detector
from ai_engine.tracking.tracker import Tracker
from ai_engine.intelligence.anpr_engine import get_anpr_engine

def run_test():
    vid_path = "storage/videos/5322ac9a-ece1-44ff-a9f5-9b5614f2dae7_Automatic Number Plate Recognition (ANPR) _ Vehicle Number Plate Recognition (1).mp4"
    print("Testing pipeline on video:", vid_path)
    cap = cv2.VideoCapture(vid_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    print(f"Total frames: {total_frames}, FPS: {fps}")

    detector = Detector(model_path="models/yolov8n.pt", conf_threshold=0.25)
    tracker = Tracker()
    anpr = get_anpr_engine()
    anpr.clear_cache()

    sample_step = max(1, int(round(fps / 5.0))) # 5 fps
    print(f"Sample step: {sample_step}")

    detected_plates = {}
    frame_idx = 0
    start_t = time.time()

    # Test frames 400 to 650 where Honda Amaze and BMW pass
    cap.set(cv2.CAP_PROP_POS_FRAMES, 420)
    frame_idx = 420

    while frame_idx <= 650:
        ret, frame = cap.read()
        if not ret:
            break

        curr = frame_idx
        frame_idx += 1

        if (curr % sample_step) != 0:
            continue

        dets = detector.detect(frame, camera_id="BOP-07", track=True)
        tracks = tracker.update(dets)

        for tr in tracks:
            if tr.object_type in ["VEHICLE", "CAR", "TRUCK", "BUS", "MOTORCYCLE"]:
                v_type = tr.object_label.split(" ")[0].upper() if " " in tr.object_label else "CAR"
                eval_res = anpr.evaluate_vehicle_plate(
                    frame_bgr=frame,
                    vehicle_bbox=tr.bbox,
                    camera_id="BOP-07",
                    track_id=tr.track_id,
                    vehicle_type=v_type
                )
                if eval_res.get("plate_status") == "READABLE" and eval_res.get("plate_text"):
                    p_txt = eval_res["plate_text"]
                    if p_txt not in detected_plates:
                        detected_plates[p_txt] = {
                            "frame": curr,
                            "track_id": tr.track_id,
                            "conf": eval_res.get("plate_confidence"),
                            "time_sec": round(curr / fps, 2)
                        }
                        print(f"--> [ANPR HIT] Frame {curr} (T+{curr/fps:.1f}s) Track #{tr.track_id}: {p_txt} (Conf: {eval_res.get('plate_confidence')}%)")

    elapsed = time.time() - start_t
    print(f"\nProcessed 230 frames in {elapsed:.2f} seconds ({230/elapsed:.1f} FPS)!")
    print("Detected plates summary:", detected_plates)
    assert any("KA" in k for k in detected_plates), "Expected at least one Karnataka plate detected!"
    print("\n[SUCCESS] Pipeline verified!")

if __name__ == '__main__':
    run_test()
