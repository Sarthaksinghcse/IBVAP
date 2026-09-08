"""
Layer 2 Unsupervised Anomaly Scoring Module — Online Normalcy Model
====================================================================
Maintains an 8x8 grid statistical model (running mean and variance of spatial
occupancy, motion magnitude, and flow direction) learned from normal operations.
Calculates normalized Mahalanobis distance anomaly scores per cell and generates an
8x8 anomaly heatmap matrix for visual overlay. Self-calibrates online during normal
frames and freezes updates when Layer-1 rules fire to prevent learning threats as normal.
"""
import numpy as np
import logging
from typing import List, Tuple, Dict, Optional
from ai_engine.intelligence.behaviour.track_state import TrackState

logger = logging.getLogger("behaviour.anomaly")


class GridAnomalyModel:
    """
    Unsupervised online grid normalcy model.
    Feature vector per cell: [occupancy_count, mean_speed_pct_s, mean_direction_rad]
    """

    def __init__(self, rows: int = 8, cols: int = 8, learning_rate: float = 0.01, threshold: float = 3.0):
        self.rows: int = rows
        self.cols: int = cols
        self.learning_rate: float = learning_rate
        self.threshold: float = threshold

        # Learned statistical distribution per cell (3 features)
        # Features: [0: occupancy, 1: speed, 2: dir_sin, 3: dir_cos] -> 4D feature vector
        self.feature_dim: int = 4
        self.mean: np.ndarray = np.zeros((rows, cols, self.feature_dim), dtype=np.float32)
        self.var: np.ndarray = np.ones((rows, cols, self.feature_dim), dtype=np.float32)  # default var = 1.0
        self.samples_seen: int = 0

        # Current frame heatmap matrix
        self.current_heatmap: np.ndarray = np.zeros((rows, cols), dtype=np.float32)

    def extract_frame_features(self, tracks: List[TrackState]) -> np.ndarray:
        """Accumulate track observations into an (8, 8, 4) grid feature matrix."""
        grid_feats = np.zeros((self.rows, self.cols, self.feature_dim), dtype=np.float32)
        grid_counts = np.zeros((self.rows, self.cols), dtype=np.float32)

        for trk in tracks:
            cx, cy = trk.current_centroid
            # Map % coords (0-100) to grid indices (0..rows-1, 0..cols-1)
            r = int(np.clip(cy / 100.0 * self.rows, 0, self.rows - 1))
            c = int(np.clip(cx / 100.0 * self.cols, 0, self.cols - 1))

            rad = np.radians(trk.direction_deg)
            sin_d = np.sin(rad)
            cos_d = np.cos(rad)

            grid_feats[r, c, 0] += 1.0                 # Occupancy count
            grid_feats[r, c, 1] += trk.speed_pct_s     # Speed
            grid_feats[r, c, 2] += sin_d               # Direction sin
            grid_feats[r, c, 3] += cos_d               # Direction cos
            grid_counts[r, c] += 1.0

        # Average motion metrics in occupied cells
        mask = grid_counts > 0
        for f in range(1, 4):
            grid_feats[:, :, f] = np.where(mask, grid_feats[:, :, f] / np.maximum(grid_counts, 1.0), 0.0)

        return grid_feats

    def evaluate_and_update(self, tracks: List[TrackState], freeze_update: bool = False) -> Tuple[float, str, dict, np.ndarray]:
        """
        Evaluate frame features against learned normalcy distribution.

        Returns:
            Tuple of: (overall_anomaly_score, reason, evidence_dict, heatmap_matrix)
        """
        frame_feats = self.extract_frame_features(tracks)

        # Compute normalized distance (squared Z-score) per cell & feature
        epsilon = 1e-4
        std = np.sqrt(np.maximum(self.var, epsilon))
        z_scores = np.abs(frame_feats - self.mean) / std

        # Cell anomaly score = max z-score across feature dimensions
        cell_scores = np.max(z_scores, axis=-1)
        # Suppress completely empty grid cells (where feature is 0 and mean is 0)
        cell_scores = np.where(frame_feats[:, :, 0] > 0, cell_scores, 0.0)

        self.current_heatmap = cell_scores.astype(np.float32)
        max_score = float(np.max(cell_scores)) if cell_scores.size > 0 else 0.0

        # Identify top contributing cell and feature
        reason = ""
        evidence = {}

        if max_score >= self.threshold:
            max_idx = np.unravel_index(np.argmax(cell_scores), cell_scores.shape)
            r, c = max_idx
            feat_idx = int(np.argmax(z_scores[r, c]))
            feat_names = ["occupancy", "speed", "flow_sin", "flow_cos"]
            feat_name = feat_names[feat_idx] if feat_idx < len(feat_names) else "motion"

            norm_val = 1.0 / (1.0 + np.exp(-0.5 * (max_score - self.threshold))) # Sigmoid normalization 0-1
            reason = f"Unusual motion in cell ({r},{c}): {feat_name} anomaly (score {max_score:.1f})"
            evidence = {
                "primitive": "unsupervised_anomaly",
                "score": round(max_score, 2),
                "norm_score": round(norm_val, 2),
                "cell_row": r,
                "cell_col": c,
                "contributing_feature": feat_name
            }

        # Online calibration update (only when no Layer 1 rules fire)
        if not freeze_update:
            self.samples_seen += 1
            lr = self.learning_rate if self.samples_seen > 50 else 0.1 # Warm-start fast then stabilize
            delta = frame_feats - self.mean
            self.mean += lr * delta
            self.var += lr * (delta**2 - self.var)

        return max_score, reason, evidence, self.current_heatmap
