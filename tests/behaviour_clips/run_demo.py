"""
IBVAP Behaviour Analysis Demo Harness & Interactive Visualizer
===============================================================
Executes live or recorded video through YOLOv8, Object Tracker, and BehaviourEngine.
Renders on-screen overlays:
- Bounding boxes with Track ID, Class, and Scale-Invariant Speed
- Polygon Zone boundaries
- Layer 2 Unsupervised Grid Anomaly Heatmap Matrix
- Live Alert Panel with human-readable reasons and evidence
"""
import os
import sys
import time
import argparse
import cv2
import numpy as np

# Ensure project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_engine.detection.detector import Detector
from ai_engine.tracking.tracker import Tracker
from ai_engine.intelligence.behaviour.behaviour_engine import BehaviourEngine


def overlay_heatmap(frame: np.ndarray, heatmap: np.ndarray, alpha: float = 0.35) -> np.ndarray:
    """Render 8x8 anomaly heatmap grid onto the video frame."""
    h, w = frame.shape[:2]
    # Resize 8x8 matrix to full frame dimensions
    norm_map = np.clip(heatmap / 5.0, 0.0, 1.0)
    map_uint8 = (norm_map * 255).astype(np.uint8)
    color_map = cv2.applyColorMap(map_uint8, cv2.COLORMAP_JET)
    color_map = cv2.resize(color_map, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.addWeighted(color_map, alpha, frame, 1.0 - alpha, 0)


def draw_side_panel(frame: np.ndarray, active_alerts: list, fps: float) -> np.ndarray:
    """Draw side panel showing active alerts, human-readable reasons, and telemetry."""
    h, w = frame.shape[:2]
    panel_w = 400
    canvas = np.zeros((h, w + panel_w, 3), dtype=np.uint8)
    canvas[:, :w] = frame

    # Panel Background
    cv2.rectangle(canvas, (w, 0), (w + panel_w, h), (20, 24, 30), -1)
    cv2.line(canvas, (w, 0), (w, h), (0, 255, 204), 2)

    # Header
    cv2.putText(canvas, "BEHAVIOUR ANALYTICS", (w + 15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 204), 2)
    cv2.putText(canvas, f"FPS: {fps:.1f} (CPU)", (w + 15, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    cv2.line(canvas, (w + 15, 80), (w + panel_w - 15, 80), (60, 60, 60), 1)

    # Alerts List
    cv2.putText(canvas, "LIVE ALERTS & EVIDENCE", (w + 15, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    y = 135
    for alert in active_alerts[-6:]: # Show up to 6 recent alerts
        level = alert.get("threat_level", "MEDIUM")
        color = (0, 0, 255) if level == "CRITICAL" else (0, 165, 255) if level == "HIGH" else (0, 255, 255)

        event_str = f"[{level}] {alert.get('event_type')}"
        cv2.putText(canvas, event_str, (w + 15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        y += 20

        reason_str = alert.get("reason", "")
        # Word wrap reason string
        words = reason_str.split(" ")
        line = ""
        for word in words:
            if len(line + " " + word) > 38:
                cv2.putText(canvas, line, (w + 20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
                y += 18
                line = word
            else:
                line = line + (" " if line else "") + word
        if line:
            cv2.putText(canvas, line, (w + 20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            y += 22
        y += 8

    return canvas


def run_demo(source: str, model_path: str = "E:/IBVAP/models/yolov8n.pt", show_heatmap: bool = True):
    """Run interactive visualizer demo."""
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"Error: Could not open video source '{source}'")
        return

    detector = Detector(model_path=model_path, conf_threshold=0.35)
    tracker = Tracker()
    behaviour_engine = BehaviourEngine(enabled=True)

    recent_alerts = []
    start_time = time.time()
    frame_count = 0

    print("--> Starting Behaviour Engine Demo Harness. Press 'q' to quit, 'h' to toggle heatmap.")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            t0 = time.time()
            frame_count += 1

            # 1. Detection & Tracking
            detections = detector.detect(frame, camera_id="BOP-07", track=True)
            active_tracks = tracker.update(detections)

            # 2. Behaviour Intelligence Analysis
            alerts = behaviour_engine.process(
                camera_id="BOP-07",
                frame=frame,
                tracks=active_tracks,
                timestamp=t0
            )

            if alerts:
                recent_alerts.extend(alerts)
                if len(recent_alerts) > 20:
                    recent_alerts = recent_alerts[-20:]

            # 3. Render Heatmap Overlay
            if show_heatmap:
                heatmap = behaviour_engine.get_anomaly_heatmap()
                frame = overlay_heatmap(frame, heatmap, alpha=0.30)

            # 4. Render Bboxes and Tracks
            h, w = frame.shape[:2]
            for trk in active_tracks:
                bx = int(trk.bbox["x"] / 100.0 * w)
                by = int(trk.bbox["y"] / 100.0 * h)
                bw = int(trk.bbox["w"] / 100.0 * w)
                bh = int(trk.bbox["h"] / 100.0 * h)

                st = behaviour_engine.track_states.get(trk.track_id)
                speed_str = f"{st.speed_h_s:.1f} h/s" if st else ""

                cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
                label = f"{trk.object_label} ({speed_str})"
                cv2.putText(frame, label, (bx, max(15, by - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # 5. Calculate FPS
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0.0

            # 6. Render Side Panel & Display
            combined = draw_side_panel(frame, recent_alerts, fps)
            cv2.imshow("IBVAP Behaviour Analytics Demo", combined)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('h'):
                show_heatmap = not show_heatmap
                print(f"Heatmap Overlay: {'ON' if show_heatmap else 'OFF'}")

    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IBVAP Behaviour Engine Visualizer Demo")
    parser.add_argument("--source", default="E:/IBVAP/storage/videos/test_border.mp4", help="Video source file")
    parser.add_argument("--model",  default="E:/IBVAP/models/yolov8n.pt", help="YOLOv8 model path")
    parser.add_argument("--no-heatmap", action="store_true", help="Disable initial heatmap overlay")
    args = parser.parse_args()

    run_demo(args.source, args.model, show_heatmap=not args.no_heatmap)
