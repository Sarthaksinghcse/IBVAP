"""
IBVAP Backend — Night Vision Runtime Configuration & Analytics Routes
======================================================================
Provides runtime controls to inspect and adjust low-light enhancement tunables
without restarting the backend services, plus statistics on enhanced detections.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.database import get_db
from models.models import Detection
from schemas.schemas import (
    NightVisionConfigUpdate,
    NightVisionStatsResponse,
)
from ai_engine.night_vision import (
    get_runtime_config,
    update_runtime_config,
    NightVisionConfig,
    DEFAULT_CONFIG,
    VALID_MODES,
    PROFILE_ORDER,
)

logger = logging.getLogger("night_vision_routes")
router = APIRouter()


@router.get("/config")
def get_config():
    """Return active process-wide night vision configuration and valid options."""
    cfg = get_runtime_config()
    return {
        "config": cfg.to_dict(),
        "valid_modes": list(VALID_MODES),
        "valid_profiles": list(PROFILE_ORDER),
        "valid_denoise_methods": ["BILATERAL", "NLM", "NONE"],
    }


@router.patch("/config")
def patch_config(data: NightVisionConfigUpdate):
    """
    Partially update night vision configuration.
    Changes are validated atomically before committing; invalid updates leave
    the active configuration intact.
    """
    patch_dict = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not patch_dict:
        return {"status": "ok", "config": get_runtime_config().to_dict(), "message": "No changes provided."}

    try:
        updated_cfg = update_runtime_config(patch_dict)
        logger.info(f"[NightVision] Runtime configuration updated: {patch_dict}")
        return {
            "status": "ok",
            "config": updated_cfg.to_dict(),
            "message": "Night vision configuration updated successfully.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/config/reset")
def reset_config():
    """Restore benchmark-tuned defaults for night vision enhancement."""
    defaults = DEFAULT_CONFIG.to_dict()
    updated_cfg = update_runtime_config(defaults)
    logger.info("[NightVision] Restored benchmark-tuned default configuration.")
    return {
        "status": "ok",
        "config": updated_cfg.to_dict(),
        "message": "Night vision configuration reset to benchmark-tuned defaults.",
    }


@router.get("/stats", response_model=NightVisionStatsResponse)
def get_stats(db: Session = Depends(get_db)):
    """
    Aggregate database statistics on recorded detections:
    total detections, enhanced count, enhanced percentage, and lighting profile breakdown.
    """
    total = db.query(func.count(Detection.id)).scalar() or 0
    enhanced = (
        db.query(func.count(Detection.id))
        .filter(Detection.night_vision_applied == True)
        .scalar()
        or 0
    )

    # Breakdown by lighting profile
    breakdown_rows = (
        db.query(Detection.lighting_profile, func.count(Detection.id))
        .group_by(Detection.lighting_profile)
        .all()
    )
    profile_breakdown = {row[0] or "UNKNOWN": row[1] for row in breakdown_rows}

    pct = round((enhanced / total * 100.0), 2) if total > 0 else 0.0

    return NightVisionStatsResponse(
        total_detections=total,
        enhanced_detections=enhanced,
        enhanced_percentage=pct,
        profile_breakdown=profile_breakdown,
        active_mode=get_runtime_config().mode,
    )
