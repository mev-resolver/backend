import asyncio, logging, time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.database import init_db, store_event
from app.api import ws as ws_mod, dex, attack, stats, events
from app.api.ws import manager
from app.core.detection import detection_engine, SandwichAttack
from app.core.mitigation import mitigation_engine
from app.core.settlement import settlement_engine
from app.core.simulator import attack_simulator
from app.services.price_drift import price_drift_service

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def _on_attack(attack: SandwichAttack) -> None:
    from app.models.database import store_attack
    det_ms = int((time.time() - attack.detected_at) * 1000) + 150
    store_attack({
        "attack_id": attack.attack_id,
        "victim_tx_hash": attack.victim_tx.tx_hash,
        "buy_tx_hash":  attack.buy_tx.tx_hash,
        "sell_tx_hash": attack.sell_tx.tx_hash,
        "confidence": attack.confidence,
        "mitigated": 0,
        "detection_latency_ms": det_ms,
        "created_at": attack.detected_at,
    })
    payload = {
        "attack_id": attack.attack_id,
        "victim_tx_hash": attack.victim_tx.tx_hash,
        "buy_tx_hash":  attack.buy_tx.tx_hash,
        "sell_tx_hash": attack.sell_tx.tx_hash,
        "confidence": attack.confidence,
        "detection_latency_ms": det_ms,
    }
    store_event("attack_detected", payload)
    await manager.broadcast({"type": "attack_detected", "data": payload, "timestamp": time.time()})
    await mitigation_engine.handle_attack(attack)


async def _mempool_watcher() -> None:
    """Subscribe to Sepolia pending transactions and run them through detection."""
    if not settings.SEPOLIA_RPC_URL:
        logger.warning("SEPOLIA_RPC_URL not set - mempool watcher disabled")
        return
    dex_addr = (settings.DEX_CONTRACT_ADDRESS or "").lower()
    if not dex_addr:
        logger.warning("DEX_CONTRACT_ADDRESS not set - mempool watcher disabled")
        return

    wss_url = (settings.SEPOLIA_RPC_URL
               .replace("https://", "wss://")
               .replace("http://", "ws://"))
    logger.info("Mempool watcher connecting to %s", wss_url)

    backoff = 5
    while True:
        try:
            from web3 import AsyncWeb3, WebSocketProvider
            async with AsyncWeb3(WebSocketProvider(wss_url)) as w3:
                logger.info("Mempool watcher live on Sepolia")
                backoff = 5
                async for tx_hash in await w3.eth.subscribe("newPendingTransactions"):
                    try:
                        tx = await w3.eth.get_transaction(tx_hash)
                        if tx and tx.get("to") and tx["to"].lower() == dex_addr:
                            await detection_engine.process_raw(
                                tx_hash=tx_hash.hex(),
                                sender=tx["from"],
                                calldata=tx["input"].hex(),
                                gas_price=int(tx.get("gasPrice") or tx.get("maxFeePerGas") or 0),
                            )
                    except Exception:
                        pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Mempool watcher error: %s - retrying in %ds", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Resolver v1.0 starting ===")
    init_db()

    missing = settings.validate_required()
    if missing:
        logger.warning("MISSING CONFIGURATION: %s", ", ".join(missing))
        logger.warning("Set these in .env to enable live blockchain features.")
    else:
        logger.info("All configuration present - live mode active")

    detection_engine.subscribe(_on_attack)
    mitigation_engine.subscribe(settlement_engine.on_bundle_settled)
    mitigation_engine.start()

    tasks = [
        asyncio.create_task(price_drift_service.run()),
        asyncio.create_task(_mempool_watcher()),
    ]
    logger.info("All services ready.")
    yield

    attack_simulator.stop()
    mitigation_engine.stop()
    for t in tasks:
        t.cancel()
    logger.info("=== Resolver stopped ===")


app = FastAPI(title="Resolver MEV API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(ws_mod.router)
app.include_router(dex.router,    prefix="/api/dex",    tags=["DEX"])
app.include_router(attack.router, prefix="/api/attack", tags=["Attack"])
app.include_router(stats.router,  prefix="/api/stats",  tags=["Stats"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])


@app.get("/health")
async def health():
    from app.models.database import get_summary_stats
    missing = settings.validate_required()
    return {
        "status": "ok",
        "version": "1.0.0",
        "live_mode": len(missing) == 0,
        "missing_config": missing,
        "ws_clients": manager.client_count,
        "stats": get_summary_stats(),
    }
