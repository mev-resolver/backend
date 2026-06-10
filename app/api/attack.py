import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.simulator import attack_simulator
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


class AutoReq(BaseModel):
    enabled: bool
    interval_seconds: int = 10


def _assert_configured():
    missing = settings.validate_required()
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Blockchain not configured. Missing .env keys: {', '.join(missing)}. See guide.md."
        )


@router.post("/manual")
async def manual_attack():
    _assert_configured()
    result = await attack_simulator.perform_sandwich()
    return {"status": "triggered", "result": result}


@router.post("/auto")
async def auto_attack(req: AutoReq):
    _assert_configured()
    if req.enabled:
        attack_simulator.start_auto(req.interval_seconds)
        return {"status": "started", "interval": req.interval_seconds}
    attack_simulator.stop_auto()
    return {"status": "stopped"}


@router.get("/status")
async def attack_status():
    missing = settings.validate_required()
    return {
        "auto_running":   attack_simulator.is_auto_running,
        "configured":     len(missing) == 0,
        "missing_config": missing,
    }
