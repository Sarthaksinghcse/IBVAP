"""
IBVAP Night Vision — Configuration
==================================
Central, serialisable configuration for the low-light enhancement layer.

Every tunable lives here so the pipeline, the FastAPI routes and the benchmark
harness all read the same defaults, and so a single settings payload from the
dashboard can reconfigure enhancement at runtime.
"""
from dataclasses import dataclass, asdict, field, fields
from typing import Any, Dict


# ─── Enhancement Modes ────────────────────────────────────────────────────────

MODE_OFF = "OFF"        # Never enhance — raw frame goes straight to YOLO
MODE_AUTO = "AUTO"      # Enhance only when measured luminance says it is dark
MODE_ALWAYS = "ALWAYS"  # Always enhance, regardless of measured luminance

VALID_MODES = (MODE_OFF, MODE_AUTO, MODE_ALWAYS)


# ─── Lighting Profiles (classified from measured frame luminance) ─────────────

PROFILE_DAY = "DAY"                # Well lit — enhancement is unnecessary
PROFILE_DUSK = "DUSK"              # Fading light — gentle enhancement
PROFILE_NIGHT = "NIGHT"            # Dark — full enhancement
PROFILE_EXTREME_LOW = "EXTREME_LOW"  # Near-black — maximum gain + denoising

# Ordered dark→light so a profile can be compared by index.
PROFILE_ORDER = (PROFILE_EXTREME_LOW, PROFILE_NIGHT, PROFILE_DUSK, PROFILE_DAY)


@dataclass
class NightVisionConfig:
    """
    Tunables for the night vision enhancement layer.

    Luminance values are mean L-channel intensity in CIELAB, 0 (black) - 255 (white).
    """

    # ── Master control ────────────────────────────────────────────────────────
    mode: str = MODE_AUTO

    # ── Lighting classification thresholds (mean LAB L-channel) ───────────────
    # A frame darker than `dusk_threshold` is a candidate for enhancement.
    dusk_threshold: float = 110.0
    night_threshold: float = 70.0
    extreme_low_threshold: float = 35.0

    # Hysteresis band. Once enhancement is engaged it stays engaged until
    # luminance climbs `hysteresis_margin` above `dusk_threshold`. Without this,
    # a frame hovering at the boundary flickers between enhanced and raw, which
    # destabilises both the tracker and the detection confidence scores.
    hysteresis_margin: float = 12.0

    # Re-classify lighting only every Nth processed frame. Luminance changes on
    # the order of minutes, not frames, so sampling keeps the cost negligible.
    luminance_sample_interval: int = 15

    # Downscale factor used when measuring luminance. Measuring on a thumbnail
    # is ~50x cheaper and statistically identical for a mean.
    luminance_downscale: int = 8

    # ── CLAHE (contrast limited adaptive histogram equalisation) ──────────────
    # Applied to the L channel only, so colour (a, b) is left untouched.
    clahe_tile_grid: int = 8
    clahe_clip_dusk: float = 1.8
    clahe_clip_night: float = 2.5
    clahe_clip_extreme: float = 3.5

    # ── Gamma correction (gamma < 1.0 brightens midtones) ─────────────────────
    gamma_dusk: float = 0.95
    gamma_night: float = 0.80
    gamma_extreme: float = 0.65

    # ── Denoising ─────────────────────────────────────────────────────────────
    # Amplifying a dark frame amplifies sensor noise with it, so denoising is
    # applied after gain. Bilateral is edge-preserving and fast enough for the
    # live path; non-local means is far higher quality but ~100x slower, so it
    # is opt-in for offline/forensic runs only.
    denoise_enabled: bool = True
    denoise_method: str = "BILATERAL"   # BILATERAL | NLM | NONE
    bilateral_diameter: int = 5
    bilateral_sigma_color: float = 45.0
    bilateral_sigma_space: float = 45.0
    # Denoise only at or below this profile (dusk frames rarely need it).
    denoise_min_profile: str = PROFILE_NIGHT

    # ── Sharpening (unsharp mask, recovers edges softened by denoising) ───────
    sharpen_enabled: bool = True
    sharpen_amount: float = 0.55
    sharpen_blur_sigma: float = 1.2

    # ── Safety rails ──────────────────────────────────────────────────────────
    # If enhancement takes longer than this per frame, log a warning. Enhancement
    # that costs more than inference is a bad trade in a real-time pipeline.
    slow_frame_warn_ms: float = 40.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NightVisionConfig":
        """Build a config from a partial dict, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (data or {}).items() if k in known}
        cfg = cls(**clean)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        """Raise ValueError on a configuration that cannot produce valid output."""
        if self.mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got {self.mode!r}")
        if self.denoise_method not in ("BILATERAL", "NLM", "NONE"):
            raise ValueError(f"denoise_method must be BILATERAL, NLM or NONE, got {self.denoise_method!r}")
        if self.denoise_min_profile not in PROFILE_ORDER:
            raise ValueError(f"denoise_min_profile must be one of {PROFILE_ORDER}")
        if not (self.extreme_low_threshold < self.night_threshold < self.dusk_threshold):
            raise ValueError(
                "thresholds must satisfy extreme_low < night < dusk, got "
                f"{self.extreme_low_threshold} / {self.night_threshold} / {self.dusk_threshold}"
            )
        if self.clahe_tile_grid < 1:
            raise ValueError("clahe_tile_grid must be >= 1")
        if self.luminance_sample_interval < 1:
            raise ValueError("luminance_sample_interval must be >= 1")
        if self.luminance_downscale < 1:
            raise ValueError("luminance_downscale must be >= 1")
        for name in ("gamma_dusk", "gamma_night", "gamma_extreme"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")


# Process-wide default, mutated by the backend settings route.
DEFAULT_CONFIG = NightVisionConfig()
