"""
IBVAP Real Low-Light & Night-Time Frame Enhancer
=================================================
Complete 11-step adaptive illumination, contrast, and detail enhancement
pipeline engineered for real CCTV, IR cameras, USB feeds, and video files.

Pipeline Architecture:
1. RAW FRAME INGESTION (immutability strictly guaranteed)
2. LUMINANCE & METRIC EXTRACTION (mean brightness, contrast, dark pixel ratio)
3. IR / GRAYSCALE CCTV DETECTION (prevents false color tints on night monochrome feeds)
4. DUAL-THRESHOLD TEMPORAL HYSTERESIS (prevents frame-to-frame flickering)
5. ADAPTIVE GAMMA SELECTION (tunes gamma dynamically based on scene darkness)
6. LUMINANCE-AWARE CLAHE (adaptive local histogram equalization on intensity)
7. HIGHLIGHT PROTECTION (prevents headlights, streetlamps & reflections from blowing out)
8. CHROMA RECOMBINATION (merges enhanced intensity with authentic color or clean monochrome)
9. SENSOR NOISE CONTROL (light edge-preserving bilateral filter)
10. MODERATE DETAIL SHARPENING (unsharp mask to reveal vehicle & person edges without halos)
11. TELEMETRY & STRUCTURED RUNTIME LOGGING
"""
import os
import time
import logging
from typing import Tuple, Optional, Dict, Any
import cv2
import numpy as np

logger = logging.getLogger("frame_enhancer")

# Configurable defaults via environment variables
DEFAULT_LOW_LIGHT_ENABLED   = os.getenv("LOW_LIGHT_ENABLED", "true").lower() in ("true", "1", "yes")
DEFAULT_LOW_LIGHT_THRESHOLD = float(os.getenv("LOW_LIGHT_THRESHOLD", "60.0"))
DEFAULT_LOW_LIGHT_EXIT      = float(os.getenv("LOW_LIGHT_EXIT", "72.0"))
DEFAULT_CLAHE_CLIP_LIMIT    = float(os.getenv("CLAHE_CLIP_LIMIT", "2.0"))
DEFAULT_CLAHE_TILE_GRID     = tuple(map(int, os.getenv("CLAHE_TILE_GRID", "8,8").split(",")))
DEFAULT_GAMMA_MIN           = float(os.getenv("GAMMA_MIN", "1.5"))
DEFAULT_GAMMA_MAX           = float(os.getenv("GAMMA_MAX", "2.2"))
DEFAULT_DENOISE_ENABLED     = os.getenv("DENOISE_ENABLED", "true").lower() in ("true", "1", "yes")
DEFAULT_SHARPEN_ENABLED     = os.getenv("SHARPEN_ENABLED", "true").lower() in ("true", "1", "yes")


class FrameEnhancer:
    """
    State-of-the-Art Adaptive Low-Light and Night-Time Video Frame Enhancer.
    """

    def __init__(
        self,
        clip_limit: float = DEFAULT_CLAHE_CLIP_LIMIT,
        tile_grid: tuple = DEFAULT_CLAHE_TILE_GRID,
        gamma_min: float = DEFAULT_GAMMA_MIN,
        gamma_max: float = DEFAULT_GAMMA_MAX,
        enter_threshold: float = DEFAULT_LOW_LIGHT_THRESHOLD,
        exit_threshold: float = DEFAULT_LOW_LIGHT_EXIT,
        denoise_enabled: bool = DEFAULT_DENOISE_ENABLED,
        sharpen_enabled: bool = DEFAULT_SHARPEN_ENABLED,
        enabled: bool = DEFAULT_LOW_LIGHT_ENABLED
    ):
        self.clip_limit = clip_limit
        self.tile_grid = tile_grid
        self.gamma_min = gamma_min
        self.gamma_max = gamma_max
        self.enter_threshold = enter_threshold
        self.exit_threshold = exit_threshold
        self.denoise_enabled = denoise_enabled
        self.sharpen_enabled = sharpen_enabled
        self.enabled = enabled

        # Initialize OpenCV CLAHE for local contrast equalization
        self.clahe = cv2.createCLAHE(
            clipLimit=float(clip_limit),
            tileGridSize=tile_grid
        )

        # Precompute cached Gamma LUTs in steps of 0.1 for ultra-fast O(1) lookups
        self._gamma_luts: Dict[float, np.ndarray] = {}
        for g_val in np.arange(round(gamma_min, 1), round(gamma_max + 0.15, 1), 0.1):
            g_key = round(float(g_val), 1)
            inv_g = 1.0 / max(0.01, g_key)
            self._gamma_luts[g_key] = np.array(
                [np.clip(((i / 255.0) ** inv_g) * 255.0, 0, 255).astype(np.uint8) for i in range(256)],
                dtype=np.uint8
            )

        # Temporal Hysteresis State
        self._is_low_light_active: bool = False
        self._smoothed_brightness: Optional[float] = None

        logger.info(
            f"[FrameEnhancer] Initialized | Clip: {self.clip_limit} | Grid: {self.tile_grid} | "
            f"Gamma: [{self.gamma_min:.1f} - {self.gamma_max:.1f}] | "
            f"Thresholds: [enter={self.enter_threshold} -> exit={self.exit_threshold}] | "
            f"Denoise: {self.denoise_enabled} | Sharpen: {self.sharpen_enabled} | Enabled: {self.enabled}"
        )

    def is_ir_or_grayscale(self, frame: np.ndarray) -> bool:
        """
        Determines if the video frame is effectively monochrome or infrared CCTV footage.
        Checks average color channel difference to avoid introducing synthetic rainbow tints.
        """
        if frame is None or len(frame.shape) == 2:
            return True
        if frame.shape[2] == 1:
            return True

        # Fast subsampled color variance check
        sample = frame[::4, ::4]
        b, g, r = sample[:, :, 0], sample[:, :, 1], sample[:, :, 2]
        diff_bg = np.mean(np.abs(b.astype(np.int16) - g.astype(np.int16)))
        diff_gr = np.mean(np.abs(g.astype(np.int16) - r.astype(np.int16)))
        return bool((diff_bg + diff_gr) < 8.5)

    def get_metrics(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Extracts ground-truth photometric metrics from actual frame pixels:
        - Mean Luminance (brightness) in [0.0, 255.0]
        - Contrast (standard deviation of luminance)
        - Dark Pixel Ratio (percentage of pixels < 45)
        - IR / Monochrome status
        """
        if frame is None or frame.size == 0:
            return {"brightness": 0.0, "contrast": 0.0, "dark_ratio": 0.0, "is_ir": False}

        if len(frame.shape) == 2:
            gray = frame
            is_ir = True
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            is_ir = self.is_ir_or_grayscale(frame)

        brightness = float(gray.mean())
        contrast = float(gray.std())
        dark_ratio = float(np.count_nonzero(gray < 45) / max(1, gray.size))

        return {
            "brightness": brightness,
            "contrast": contrast,
            "dark_ratio": dark_ratio,
            "is_ir": is_ir
        }

    def get_brightness(self, frame: np.ndarray) -> float:
        """Convenience method returning ground-truth grayscale mean luminance."""
        return self.get_metrics(frame)["brightness"]

    def calculate_adaptive_gamma(self, brightness: float, contrast: float, dark_ratio: float) -> float:
        """
        Dynamically calculates optimal gamma correction factor in [gamma_min, gamma_max].
        Deep night scenes with heavy shadows receive higher gamma to reveal details,
        while moderately dark scenes use moderate gamma to maintain natural contrast.
        """
        dark_factor = max(0.0, (self.enter_threshold - brightness) / max(1.0, self.enter_threshold))
        raw_gamma = self.gamma_min + (self.gamma_max - self.gamma_min) * dark_factor + (0.25 * dark_ratio)
        return float(np.clip(raw_gamma, self.gamma_min, self.gamma_max))

    def _get_gamma_lut(self, gamma_val: float) -> np.ndarray:
        """Retrieves or builds precomputed LUT for the target gamma value."""
        rounded_key = round(gamma_val, 1)
        lut = self._gamma_luts.get(rounded_key)
        if lut is None:
            inv_g = 1.0 / max(0.01, gamma_val)
            lut = np.array(
                [np.clip(((i / 255.0) ** inv_g) * 255.0, 0, 255).astype(np.uint8) for i in range(256)],
                dtype=np.uint8
            )
            self._gamma_luts[rounded_key] = lut
        return lut

    def is_low_light(self, frame: np.ndarray) -> Tuple[bool, Dict[str, Any]]:
        """
        Evaluates whether frame is in low-light condition with temporal hysteresis:
        - Enter low light when smoothed brightness < enter_threshold (e.g. 60.0).
        - Exit low light when smoothed brightness > exit_threshold (e.g. 72.0).
        - Prevents rapid toggling on intermediate illumination fluctuations.
        """
        metrics = self.get_metrics(frame)
        brightness = metrics["brightness"]

        if self._smoothed_brightness is None:
            self._smoothed_brightness = brightness
        else:
            self._smoothed_brightness = (0.4 * brightness) + (0.6 * self._smoothed_brightness)

        if not self._is_low_light_active:
            if self._smoothed_brightness < self.enter_threshold:
                self._is_low_light_active = True
                logger.info(
                    f"[LOW_LIGHT] Entered low-light mode: brightness={brightness:.1f} "
                    f"(smoothed={self._smoothed_brightness:.1f} < {self.enter_threshold})"
                )
        else:
            if self._smoothed_brightness > self.exit_threshold or brightness > (self.exit_threshold + 5.0):
                self._is_low_light_active = False
                logger.info(
                    f"[LOW_LIGHT] Exited low-light mode: brightness={brightness:.1f} "
                    f"(smoothed={self._smoothed_brightness:.1f} > {self.exit_threshold})"
                )

        return self._is_low_light_active, metrics

    def enhance(self, frame: np.ndarray) -> Tuple[np.ndarray, bool, Dict[str, Any]]:
        """
        Executes the full 11-step enhancement pipeline.
        GUARANTEE: The input `frame` is NEVER modified in-place.
        Returns:
            (enhanced_frame, was_enhanced, telemetry_dict)
        """
        if not self.enabled or frame is None or frame.size == 0:
            return frame, False, {
                "brightness": 0.0,
                "contrast": 0.0,
                "gamma": 1.0,
                "is_ir": False,
                "low_light": False,
                "enhanced": False,
                "time_ms": 0.0
            }

        is_low, metrics = self.is_low_light(frame)
        brightness = metrics["brightness"]
        contrast = metrics["contrast"]
        dark_ratio = metrics["dark_ratio"]
        is_ir = metrics["is_ir"]

        # If daylight / sufficiently lit, return untouched original raw frame with 0 overhead
        if not is_low:
            return frame, False, {
                "brightness": round(brightness, 1),
                "contrast": round(contrast, 1),
                "gamma": 1.0,
                "is_ir": is_ir,
                "low_light": False,
                "enhanced": False,
                "time_ms": 0.0
            }

        # Genuinely low-light: proceed with full adaptive enhancement
        t0 = time.perf_counter()

        # Step 1: Calculate adaptive gamma
        adaptive_gamma = self.calculate_adaptive_gamma(brightness, contrast, dark_ratio)
        gamma_lut = self._get_gamma_lut(adaptive_gamma)

        # Step 2: Separate luminance & apply CLAHE + Gamma with Highlight Protection
        if is_ir:
            # Monochrome / IR CCTV path: enhance intensity directly without artificial colors
            if len(frame.shape) == 3:
                gray_in = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray_in = frame.copy()

            # Local contrast equalization
            clahe_gray = self.clahe.apply(gray_in)

            # Adaptive gamma stretch
            gamma_gray = cv2.LUT(clahe_gray, gamma_lut)

            # Highlight protection: preserve headlights, lamps, and bright reflections
            hl_mask = np.clip((gray_in.astype(np.float32) - 175.0) / 75.0, 0.0, 1.0)
            protected_gray = ((1.0 - hl_mask) * gamma_gray.astype(np.float32) + hl_mask * gray_in.astype(np.float32)).astype(np.uint8)

            # Convert to 3-channel BGR for YOLO & display
            enhanced_bgr = cv2.cvtColor(protected_gray, cv2.COLOR_GRAY2BGR)
        else:
            # RGB Color CCTV path: enhance L channel in LAB color space
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l_chan, a_chan, b_chan = cv2.split(lab)

            # Local contrast equalization on L channel
            clahe_l = self.clahe.apply(l_chan)

            # Adaptive gamma stretch
            gamma_l = cv2.LUT(clahe_l, gamma_lut)

            # Highlight protection: prevent headlights & streetlights from overexposure
            hl_mask = np.clip((l_chan.astype(np.float32) - 175.0) / 75.0, 0.0, 1.0)
            protected_l = ((1.0 - hl_mask) * gamma_l.astype(np.float32) + hl_mask * l_chan.astype(np.float32)).astype(np.uint8)

            # Merge with authentic chrominance channels
            merged_lab = cv2.merge([protected_l, a_chan, b_chan])
            enhanced_bgr = cv2.cvtColor(merged_lab, cv2.COLOR_LAB2BGR)

        # Step 3: Sensor Noise Control (light bilateral filter preserves sharp edges)
        if self.denoise_enabled:
            # Bilateral filter smooths high-ISO CMOS noise while keeping vehicle and person edges intact
            enhanced_bgr = cv2.bilateralFilter(enhanced_bgr, d=5, sigmaColor=20, sigmaSpace=20)

        # Step 4: Moderate Detail Sharpening (unsharp mask without halo artifacts)
        if self.sharpen_enabled:
            gaussian = cv2.GaussianBlur(enhanced_bgr, (0, 0), sigmaX=1.5)
            enhanced_bgr = cv2.addWeighted(enhanced_bgr, 1.25, gaussian, -0.25, 0)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        telemetry = {
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "gamma": round(adaptive_gamma, 2),
            "is_ir": is_ir,
            "low_light": True,
            "enhanced": True,
            "time_ms": round(elapsed_ms, 2)
        }

        # Structured diagnostic log
        logger.info(
            f"[FRAME] brightness={brightness:.1f} contrast={contrast:.1f} is_ir={is_ir} | "
            f"[ENHANCER] low_light=True gamma={adaptive_gamma:.2f} clahe_applied=True "
            f"denoise={self.denoise_enabled} sharpen={self.sharpen_enabled} processing_ms={elapsed_ms:.1f}ms"
        )

        return enhanced_bgr, True, telemetry

    def reset(self):
        """Resets temporal smoothing state between separate video jobs or stream reconnects."""
        self._is_low_light_active = False
        self._smoothed_brightness = None


# Global singleton instance
_global_enhancer: Optional[FrameEnhancer] = None


def get_frame_enhancer(**kwargs) -> FrameEnhancer:
    """Returns or creates the shared global FrameEnhancer instance."""
    global _global_enhancer
    if _global_enhancer is None:
        _global_enhancer = FrameEnhancer(**kwargs)
    return _global_enhancer
