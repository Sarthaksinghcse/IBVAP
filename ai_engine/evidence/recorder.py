"""
IBVAP Evidence Recorder — Forensic Snapshot Capture
===================================================
Captures and annotates full-frame JPEG snapshots on HIGH and CRITICAL alerts.

Snapshots burn in the camera identity, UTC timestamp, event type, threat level,
and lighting/night-vision provenance so that investigators have immediate,
self-contained visual evidence.
"""
import os
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import cv2
import numpy as np

logger = logging.getLogger("evidence_recorder")


class EvidenceRecorder:
    """
    Forensic evidence snapshot recorder.
    Saves annotated JPEG snapshots under storage/snapshots/YYYY-MM-DD/<camera_id>/.
    """

    def __init__(self, storage_root: Optional[str] = None):
        if storage_root is None:
            # Default to <project_root>/storage
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            storage_root = os.path.join(base_dir, "storage")
        self.storage_root = storage_root
        self.snapshots_dir = os.path.join(self.storage_root, "snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)

    def record_alert_snapshot(
        self,
        frame_bgr: np.ndarray,
        camera_id: str,
        event_type: str,
        threat_level: str,
        bbox: Optional[Dict[str, float]] = None,
        lighting_profile: Optional[str] = None,
        frame_luminance: Optional[float] = None,
        night_vision_applied: Optional[bool] = None,
        timestamp: Optional[datetime] = None,
        object_label: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create and persist an annotated forensic JPEG for an alert.

        Returns relative path (e.g. 'storage/snapshots/2026-09-08/BOP-07/ZONE_INTRUSION_123045_a1b2c3d4.jpg')
        or None if frame is missing or an error occurs.
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return None

        # Only record evidence snapshots for HIGH and CRITICAL severity
        if threat_level not in ("HIGH", "CRITICAL"):
            return None

        try:
            ts = timestamp or datetime.utcnow()
            date_str = ts.strftime("%Y-%m-%d")
            time_str = ts.strftime("%H%M%S")
            short_id = uuid.uuid4().hex[:8]

            safe_cam = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (camera_id or "CAM"))
            safe_evt = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (event_type or "EVENT"))

            dir_path = os.path.join(self.snapshots_dir, date_str, safe_cam)
            os.makedirs(dir_path, exist_ok=True)

            filename = f"{safe_evt}_{time_str}_{short_id}.jpg"
            full_path = os.path.join(dir_path, filename)

            # Create annotated copy so input frame is not mutated
            annotated = frame_bgr.copy()
            h, w = annotated.shape[:2]

            # 1. Draw target bounding box if provided (percentages 0-100)
            if bbox and isinstance(bbox, dict):
                bx = int((bbox.get("x", 0.0) / 100.0) * w)
                by = int((bbox.get("y", 0.0) / 100.0) * h)
                bw = int((bbox.get("w", 0.0) / 100.0) * w)
                bh = int((bbox.get("h", 0.0) / 100.0) * h)

                box_color = (0, 0, 255) if threat_level == "CRITICAL" else (0, 165, 255)
                cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), box_color, 2)
                if object_label:
                    cv2.putText(
                        annotated,
                        f"{object_label}",
                        (bx, max(18, by - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        box_color,
                        2,
                    )

            # 2. Draw Top Forensic Banner
            banner_h = max(34, int(h * 0.05))
            overlay = annotated.copy()
            cv2.rectangle(overlay, (0, 0), (w, banner_h), (20, 20, 20), -1)
            cv2.addWeighted(overlay, 0.75, annotated, 0.25, 0, annotated)

            # Banner border
            border_color = (0, 0, 255) if threat_level == "CRITICAL" else (0, 165, 255)
            cv2.line(annotated, (0, banner_h), (w, banner_h), border_color, 2)

            # Left text: Alert Threat + Event + Camera
            header_text = f"[{threat_level}] {event_type} | CAM: {camera_id} | {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            cv2.putText(
                annotated,
                header_text,
                (10, int(banner_h * 0.68)),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.45, w / 1600.0),
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            # Right text: Night Vision Provenance
            nv_status = "ACTIVE" if night_vision_applied else "PASSTHROUGH"
            prof_str = lighting_profile or "UNKNOWN"
            lum_str = f"L={frame_luminance:.1f}" if frame_luminance is not None else "L=N/A"
            provenance_text = f"NV: {nv_status} ({prof_str}, {lum_str})"

            (tw, _), _ = cv2.getTextSize(provenance_text, cv2.FONT_HERSHEY_SIMPLEX, max(0.42, w / 1700.0), 1)
            cv2.putText(
                annotated,
                provenance_text,
                (max(10, w - tw - 12), int(banner_h * 0.68)),
                cv2.FONT_HERSHEY_SIMPLEX,
                max(0.42, w / 1700.0),
                (0, 255, 255) if night_vision_applied else (200, 200, 200),
                1,
                cv2.LINE_AA,
            )

            # 3. Write JPEG image
            cv2.imwrite(full_path, annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
            rel_path = f"storage/snapshots/{date_str}/{safe_cam}/{filename}"
            logger.info(f"[EvidenceRecorder] Saved alert evidence snapshot: {rel_path}")
            return rel_path

        except Exception as e:
            # Evidence recording is best-effort: alert firing must never fail due to snapshot capture
            logger.error(f"[EvidenceRecorder] Failed to capture snapshot: {e}", exc_info=True)
            return None


_global_recorder: Optional[EvidenceRecorder] = None


def get_evidence_recorder() -> EvidenceRecorder:
    """Singleton getter for the evidence snapshot recorder."""
    global _global_recorder
    if _global_recorder is None:
        _global_recorder = EvidenceRecorder()
    return _global_recorder
