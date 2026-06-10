import time
from fastapi import APIRouter
from app.models.database import get_events, get_events_in_range

router = APIRouter()

@router.get("/")
async def list_events(limit: int = 100, offset: int = 0):
    evts = get_events(limit, offset)
    return {"events": evts, "total": len(evts)}

@router.get("/replay")
async def replay_events(start_ts: float = 0.0, end_ts: float = 0.0):
    if end_ts == 0.0: end_ts = time.time()
    if start_ts == 0.0: start_ts = end_ts - 3600
    return {"events": get_events_in_range(start_ts, end_ts),
            "start_ts": start_ts, "end_ts": end_ts}
