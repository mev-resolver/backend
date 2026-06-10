from fastapi import APIRouter
from app.models.database import get_summary_stats, get_transactions

router = APIRouter()

@router.get("/summary")
async def summary():
    return get_summary_stats()

@router.get("/history")
async def history(limit: int = 50):
    txs = get_transactions(limit)
    return {"transactions": txs, "total": len(txs)}
