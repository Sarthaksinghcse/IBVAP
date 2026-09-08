"""
IBVAP Night Vision Module
=========================
Low-light frame enhancement applied before YOLOv8 inference.

Typical use — one enhancer per video stream:

    from ai_engine.night_vision import get_enhancer

    enhancer = get_enhancer()               # honours the global runtime config
    result = enhancer.process(frame)
    detections = detector.detect(result.frame, camera_id=cam, track=True)
    # result.applied / result.reason / result.lighting.profile  -> telemetry
"""
from typing import Optional, Dict, Any

from .config import (
    NightVisionConfig,
    DEFAULT_CONFIG,
    MODE_OFF, MODE_AUTO, MODE_ALWAYS, VALID_MODES,
    PROFILE_DAY, PROFILE_DUSK, PROFILE_NIGHT, PROFILE_EXTREME_LOW, PROFILE_ORDER,
)
from .enhancement import NightVisionEnhancer, EnhancementResult, FrameLighting

__all__ = [
    "NightVisionConfig", "NightVisionEnhancer", "EnhancementResult", "FrameLighting",
    "MODE_OFF", "MODE_AUTO", "MODE_ALWAYS", "VALID_MODES",
    "PROFILE_DAY", "PROFILE_DUSK", "PROFILE_NIGHT", "PROFILE_EXTREME_LOW", "PROFILE_ORDER",
    "get_enhancer", "get_runtime_config", "update_runtime_config",
]


# ─── Process-wide runtime configuration ───────────────────────────────────────
# The backend settings route mutates this; each new enhancer picks it up. Live
# enhancers keep the config they were built with, so a settings change takes
# effect on the next stream rather than mid-analysis (which would make a single
# video's detections inconsistent with each other).

_runtime_config = NightVisionConfig()


def get_runtime_config() -> NightVisionConfig:
    """Return the current process-wide night vision configuration."""
    return _runtime_config


def update_runtime_config(patch: Dict[str, Any]) -> NightVisionConfig:
    """
    Merge a partial settings dict into the runtime config.

    Validates before committing, so an invalid patch leaves the previous
    configuration in place rather than half-applying.
    """
    global _runtime_config
    merged = _runtime_config.to_dict()
    merged.update(patch or {})
    _runtime_config = NightVisionConfig.from_dict(merged)  # validates
    return _runtime_config


def get_enhancer(config: Optional[NightVisionConfig] = None) -> NightVisionEnhancer:
    """
    Build a new enhancer for one video stream.

    Deliberately not a singleton: the enhancer carries per-scene lighting state
    and hysteresis, so two concurrent streams must not share one.
    """
    return NightVisionEnhancer(config or get_runtime_config())
