import time, random, logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.services.price_drift import price_drift_service
from app.models.database import store_transaction, store_event
from app.api.ws import manager

router = APIRouter()
logger = logging.getLogger(__name__)
EXPLORER = "https://sepolia.etherscan.io/tx/"


class SwapRequest(BaseModel):
    token_in: str
    token_out: str
    amount_in: float
    min_amount_out: float = 0.0
    sender: Optional[str] = "0xdemo"

class LiquidityRequest(BaseModel):
    token_a: str; token_b: str
    amount_a: float; amount_b: float


@router.post("/swap")
async def swap(req: SwapRequest):
    from app.core.detection import detection_engine, MemTx
    tx_hash = "0x" + "".join(random.choices("0123456789abcdef", k=64))
    gas_price = random.randint(15,30) * 10**9
    amount_out = price_drift_service.get_output(req.token_in, req.amount_in)
    tx = MemTx(tx_hash=tx_hash, sender=req.sender or "0xuser",
               token_in=req.token_in, token_out=req.token_out,
               amount_in=req.amount_in, gas_price=gas_price, timestamp=time.time())
    payload = {
        "tx_hash": tx_hash, "from": tx.sender,
        "token_in": req.token_in, "token_out": req.token_out,
        "amount_in": req.amount_in, "amount_out": round(amount_out,6),
        "gas_price": gas_price, "is_bot": False, "color": "teal",
        "etherscan_url": EXPLORER + tx_hash,
    }
    store_event("transaction_arrived", payload)
    store_transaction({
        "tx_hash": tx_hash, "sender": tx.sender,
        "token_in": req.token_in, "token_out": req.token_out,
        "amount_in": req.amount_in, "gas_price": gas_price,
        "status": "submitted", "attack_id": None, "bundle_id": None,
        "created_at": time.time(), "etherscan_url": EXPLORER + tx_hash,
    })
    await manager.broadcast({"type":"transaction_arrived","data":payload,"timestamp":time.time()})
    price_drift_service.apply_swap(req.token_in, req.amount_in, amount_out)
    await detection_engine.process(tx)
    return {"tx_hash": tx_hash, "amount_out": round(amount_out,6),
            "price": round(price_drift_service.price,6),
            "etherscan_url": EXPLORER + tx_hash, "status": "submitted"}


@router.get("/price")
async def get_price(token_in: str = "RES", token_out: str = "OLV"):
    return {
        "token_in": token_in, "token_out": token_out,
        "price":       round(price_drift_service.price, 6),
        "res_reserve": round(price_drift_service.reserves["RES"], 2),
        "olv_reserve": round(price_drift_service.reserves["OLV"], 2),
        "tvl_usd":     round(price_drift_service.tvl_usd, 2),
    }


@router.post("/add_liquidity")
async def add_liquidity(req: LiquidityRequest):
    price_drift_service.reserves[req.token_a] = price_drift_service.reserves.get(req.token_a,0) + req.amount_a
    price_drift_service.reserves[req.token_b] = price_drift_service.reserves.get(req.token_b,0) + req.amount_b
    return {"status": "ok"}
