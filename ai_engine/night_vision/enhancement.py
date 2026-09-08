"""
IBVAP Night Vision — Low-Light Frame Enhancement
================================================
Classical (non-learned) enhancement applied to a BGR frame *before* YOLOv8
inference, so the detector sees a frame with usable contrast in the dark.

Pipeline
--------
    Input BGR frame
         |
    Luminance measurement  (LAB L-channel mean, on a thumbnail)
         |
    Lighting classification  ->  DAY | DUSK | NIGHT | EXTREME_LOW
         |
    [DAY, or mode=OFF]  -> return frame untouched (zero-copy, zero cost)
         |
    LAB conversion
         |
    CLAHE on L channel      (adaptive clip limit per profile)
         |
    Gamma correction        (LUT, brightens midtones)
         |
    Denoising               (bilateral; NLM opt-in for offline work)
         |
    Unsharp-mask sharpening (recovers edges softened by denoising)
         |
    Enhanced BGR frame

Design notes
------------
* Colour is preserved: CLAHE touches only L in CIELAB, never the a/b chroma
  channels, so vehicle colour and plate contrast survive intact for ANPR.
* Enhancement is *skipped entirely* on well-lit frames. Enhancing a daylight
  frame costs FPS and can flatten the contrast YOLO already relies on.
* Hysteresis prevents per-frame flapping at the light/dark boundary, which
  would otherwise destabilise tracking and confidence scores.
* Every call returns telemetry, so the pipeline can record *why* a frame was
  or was not enhanced. This keeps the explainable, non-black-box property of
  the platform intact for the night vision layer too.
"""
import time
import logging
from typing import Optional, Tuple, Dict, Any

import cv2
import numpy as np

from .config import (
    NightVisionConfig,
    MODE_OFF, MODE_AUTO, MODE_ALWAYS,
    PROFILE_DAY, PROFILE_DUSK, PROFILE_NIGHT, PROFILE_EXTREME_LOW,
    PROFILE_ORDER,
)

logger = logging.getLogger("night_vision")


class FrameLighting:
    """Measured lighting state of a single frame."""

    __slots__ = ("luminance", "contrast", "dark_pixel_ratio", "profile")

    def __init__(self, luminance: float, contrast: float, dark_pixel_ratio: float, profile: str):
        self.luminance = luminance                  # mean LAB L, 0-255
        self.contrast = contrast                    # std-dev of L, 0-255
        self.dark_pixel_ratio = dark_pixel_ratio    # fraction of L < 40
        self.profile = profile                      # DAY | DUSK | NIGHT | EXTREME_LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "luminance": round(self.luminance, 2),
            "contrast": round(self.contrast, 2),
            "dark_pixel_ratio": round(self.dark_pixel_ratio, 4),
            "profile": self.profile,
        }

    def __repr__(self) -> str:
        return (f"FrameLighting(profile={self.profile}, luminance={self.luminance:.1f}, "
                f"contrast={self.contrast:.1f}, dark={self.dark_pixel_ratio:.1%})")


class EnhancementResult:
    """Outcome of one enhancement call — the frame plus why it was treated that way."""

    __slots__ = ("frame", "applied", "reason", "lighting", "elapsed_ms")

    def __init__(self, frame: np.ndarray, applied: bool, reason: str,
                 lighting: FrameLighting, elapsed_ms: float):
        self.frame = frame              # BGR frame handed to the detector
        self.applied = applied          # was enhancement actually run?
        self.reason = reason            # human-readable explanation
        self.lighting = lighting        # measured lighting state
        self.elapsed_ms = elapsed_ms    # enhancement cost for this frame

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applied": self.applied,
            "reason": self.reason,
            "elapsed_ms": round(self.elapsed_ms, 2),
            **self.lighting.to_dict(),
        }


class NightVisionEnhancer:
    """
    Stateful low-light enhancer.

    Stateful because it caches the lighting classification between sampled
    frames and carries hysteresis across calls. Create one instance per video
    stream; do not share a single instance across concurrent streams, since the
    cached lighting state belongs to one scene.
    """

    def __init__(self, config: Optional[NightVisionConfig] = None):
        self.config = config or NightVisionConfig()
        self.config.validate()

        # Cached lighting state between sampled frames
        self._frame_counter = 0
        self._cached_lighting: Optional[FrameLighting] = None
        # Hysteresis latch: True while enhancement is engaged
        self._engaged = False

        # Running telemetry over the lifetime of this enhancer
        self.frames_seen = 0
        self.frames_enhanced = 0
        self.total_enhance_ms = 0.0

        # CLAHE objects are cheap to construct but not free; cache per clip limit.
        self._clahe_cache: Dict[float, Any] = {}
        # Gamma LUTs are 256-byte tables; cache per gamma value.
        self._gamma_lut_cache: Dict[float, np.ndarray] = {}

    # ── Lighting measurement ─────────────────────────────────────────────────

    def measure_lighting(self, frame: np.ndarray) -> FrameLighting:
        """
        Measure frame luminance and classify it into a lighting profile.

        Measured on a downscaled thumbnail: a mean and a standard deviation are
        scale-invariant enough that full-resolution measurement buys nothing.
        """
        cfg = self.config
        scale = cfg.luminance_downscale

        h, w = frame.shape[:2]
        if scale > 1 and h >= scale * 2 and w >= scale * 2:
            small = cv2.resize(frame, (max(1, w // scale), max(1, h // scale)),
                               interpolation=cv2.INTER_AREA)
        else:
            small = frame

        # L channel of CIELAB is perceptual lightness — a better brightness proxy
        # than a naive BGR mean, which over-weights green.
        lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]

        luminance = float(np.mean(l_channel))
        contrast = float(np.std(l_channel))
        dark_pixel_ratio = float(np.count_nonzero(l_channel < 40) / l_channel.size)

        if luminance < cfg.extreme_low_threshold:
            profile = PROFILE_EXTREME_LOW
        elif luminance < cfg.night_threshold:
            profile = PROFILE_NIGHT
        elif luminance < cfg.dusk_threshold:
            profile = PROFILE_DUSK
        else:
            profile = PROFILE_DAY

        return FrameLighting(luminance, contrast, dark_pixel_ratio, profile)

    def _lighting_for_frame(self, frame: np.ndarray) -> FrameLighting:
        """Return lighting for this frame, re-measuring only on sampled frames."""
        interval = self.config.luminance_sample_interval
        if self._cached_lighting is None or (self._frame_counter % interval) == 0:
            self._cached_lighting = self.measure_lighting(frame)
        self._frame_counter += 1
        return self._cached_lighting

    def _should_enhance(self, lighting: FrameLighting) -> Tuple[bool, str]:
        """
        Decide whether to enhance, applying hysteresis in AUTO mode.

        Returns (should_enhance, human_readable_reason).
        """
        cfg = self.config

        if cfg.mode == MODE_OFF:
            self._engaged = False
            return False, "Night vision disabled (mode=OFF)."

        if cfg.mode == MODE_ALWAYS:
            self._engaged = True
            return True, f"Enhancement forced (mode=ALWAYS); scene measured as {lighting.profile}."

        # AUTO — engage below the dusk threshold, disengage only once luminance
        # climbs clear of it by the hysteresis margin.
        if self._engaged:
            release_at = cfg.dusk_threshold + cfg.hysteresis_margin
            if lighting.luminance >= release_at:
                self._engaged = False
                return False, (
                    f"Scene brightened to luminance {lighting.luminance:.1f} "
                    f"(>= release threshold {release_at:.1f}); enhancement disengaged."
                )
            return True, (
                f"Low-light scene ({lighting.profile}, luminance {lighting.luminance:.1f}); "
                f"enhancement engaged."
            )

        if lighting.luminance < cfg.dusk_threshold:
            self._engaged = True
            return True, (
                f"Low-light scene detected ({lighting.profile}, luminance "
                f"{lighting.luminance:.1f} < {cfg.dusk_threshold:.1f}); enhancement engaged."
            )

        return False, (
            f"Well-lit scene (luminance {lighting.luminance:.1f} >= "
            f"{cfg.dusk_threshold:.1f}); frame passed through unmodified."
        )

    # ── Per-profile parameter selection ──────────────────────────────────────

    def _clahe_clip_for(self, profile: str) -> float:
        cfg = self.config
        return {
            PROFILE_EXTREME_LOW: cfg.clahe_clip_extreme,
            PROFILE_NIGHT: cfg.clahe_clip_night,
            PROFILE_DUSK: cfg.clahe_clip_dusk,
        }.get(profile, cfg.clahe_clip_dusk)

    def _gamma_for(self, profile: str) -> float:
        cfg = self.config
        return {
            PROFILE_EXTREME_LOW: cfg.gamma_extreme,
            PROFILE_NIGHT: cfg.gamma_night,
            PROFILE_DUSK: cfg.gamma_dusk,
        }.get(profile, cfg.gamma_dusk)

    def _get_clahe(self, clip_limit: float):
        clahe = self._clahe_cache.get(clip_limit)
        if clahe is None:
            grid = self.config.clahe_tile_grid
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid, grid))
            self._clahe_cache[clip_limit] = clahe
        return clahe

    def _get_gamma_lut(self, gamma: float) -> np.ndarray:
        lut = self._gamma_lut_cache.get(gamma)
        if lut is None:
            inv = 1.0 / gamma
            ramp = np.arange(256, dtype=np.float32) / 255.0
            lut = np.clip(np.power(ramp, inv) * 255.0, 0, 255).astype(np.uint8)
            self._gamma_lut_cache[gamma] = lut
        return lut

    def _denoise_applies_to(self, profile: str) -> bool:
        """Denoise only at or below the configured profile (darker == lower index)."""
        cfg = self.config
        if not cfg.denoise_enabled or cfg.denoise_method == "NONE":
            return False
        try:
            return PROFILE_ORDER.index(profile) <= PROFILE_ORDER.index(cfg.denoise_min_profile)
        except ValueError:
            return False

    # ── Core enhancement ─────────────────────────────────────────────────────

    def _apply_enhancement(self, frame: np.ndarray, profile: str) -> np.ndarray:
        """Run the enhancement chain. Returns a new frame; the input is untouched."""
        cfg = self.config

        # 1. CLAHE on the LAB lightness channel (chroma preserved).
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        l_ch = self._get_clahe(self._clahe_clip_for(profile)).apply(l_ch)
        out = cv2.cvtColor(cv2.merge((l_ch, a_ch, b_ch)), cv2.COLOR_LAB2BGR)

        # 2. Gamma correction to lift midtones (LUT — one pass, no per-pixel
        #    float math). gamma > 1 brightens under the 1/gamma convention below.
        gamma = self._gamma_for(profile)
        if abs(gamma - 1.0) > 1e-3:
            out = cv2.LUT(out, self._get_gamma_lut(gamma))

        # 3. Denoise — gain amplifies sensor noise, so this runs after gain.
        if self._denoise_applies_to(profile):
            if cfg.denoise_method == "BILATERAL":
                out = cv2.bilateralFilter(
                    out,
                    d=cfg.bilateral_diameter,
                    sigmaColor=cfg.bilateral_sigma_color,
                    sigmaSpace=cfg.bilateral_sigma_space,
                )
            elif cfg.denoise_method == "NLM":
                # Very high quality, very slow. Offline / forensic use only.
                out = cv2.fastNlMeansDenoisingColored(out, None, 5, 5, 7, 21)

        # 4. Unsharp mask to restore edges the denoiser softened.
        if cfg.sharpen_enabled and cfg.sharpen_amount > 0:
            blurred = cv2.GaussianBlur(out, (0, 0), cfg.sharpen_blur_sigma)
            out = cv2.addWeighted(out, 1.0 + cfg.sharpen_amount, blurred, -cfg.sharpen_amount, 0)

        return out

    # ── Public API ───────────────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> EnhancementResult:
        """
        Enhance a BGR frame if the scene warrants it.

        Always returns an EnhancementResult. When enhancement is skipped,
        `result.frame` is the original array (not a copy), so the well-lit path
        costs only the luminance measurement.
        """
        if frame is None or frame.size == 0:
            empty = FrameLighting(0.0, 0.0, 0.0, PROFILE_DAY)
            return EnhancementResult(frame, False, "Empty frame; nothing to enhance.", empty, 0.0)

        self.frames_seen += 1
        started = time.perf_counter()

        lighting = self._lighting_for_frame(frame)
        should, reason = self._should_enhance(lighting)

        if not should:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return EnhancementResult(frame, False, reason, lighting, elapsed_ms)

        try:
            enhanced = self._apply_enhancement(frame, lighting.profile)
        except cv2.error as e:
            # Never let enhancement break the surveillance pipeline — a raw frame
            # detected imperfectly beats no frame detected at all.
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.error(f"[NightVision] Enhancement failed, passing raw frame through: {e}")
            return EnhancementResult(
                frame, False, f"Enhancement error ({e}); raw frame passed through.",
                lighting, elapsed_ms
            )

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.frames_enhanced += 1
        self.total_enhance_ms += elapsed_ms

        if elapsed_ms > self.config.slow_frame_warn_ms:
            logger.warning(
                f"[NightVision] Enhancement took {elapsed_ms:.1f}ms "
                f"(> {self.config.slow_frame_warn_ms:.0f}ms budget) on a "
                f"{frame.shape[1]}x{frame.shape[0]} frame, profile={lighting.profile}."
            )

        return EnhancementResult(enhanced, True, reason, lighting, elapsed_ms)

    def enhance(self, frame: np.ndarray) -> np.ndarray:
        """Convenience wrapper returning just the frame, for drop-in call sites."""
        return self.process(frame).frame

    def reset(self) -> None:
        """Clear cached scene state. Call when the stream source changes."""
        self._frame_counter = 0
        self._cached_lighting = None
        self._engaged = False

    def stats(self) -> Dict[str, Any]:
        """Lifetime telemetry for this enhancer."""
        enhanced = self.frames_enhanced
        return {
            "mode": self.config.mode,
            "frames_seen": self.frames_seen,
            "frames_enhanced": enhanced,
            "enhancement_rate": round(enhanced / self.frames_seen, 4) if self.frames_seen else 0.0,
            "avg_enhance_ms": round(self.total_enhance_ms / enhanced, 2) if enhanced else 0.0,
            "total_enhance_ms": round(self.total_enhance_ms, 2),
            "current_profile": self._cached_lighting.profile if self._cached_lighting else None,
            "engaged": self._engaged,
        }
