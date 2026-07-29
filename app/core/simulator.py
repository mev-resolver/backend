import asyncio
import time
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)
EXPLORER = "https://sepolia.etherscan.io/tx/"

def _is_local_testnet() -> bool:
    url = settings.SEPOLIA_RPC_URL.lower()
    return "localhost" in url or "127.0.0.1" in url

def _get_gas_price_for_priority(priority: str) -> int:
    """Return gas price in wei for local testnet. For Sepolia, returns 0 (dynamic)."""
    if _is_local_testnet():
        prices = {"high": 100, "medium": 50, "low": 20}  # Gwei
        return prices.get(priority, 50) * 10**9
    return 0

def _check_config():
    missing = settings.validate_required()
    if missing:
        raise RuntimeError(
            "Cannot run attack simulator - missing .env keys: "
            + ", ".join(missing)
            + ". See .env.example for required configuration."
        )

class AttackSimulator:
    def __init__(self):
        self._auto_running = False
        self._auto_task: Optional[asyncio.Task] = None
        self._auto_interval = settings.ATTACK_AUTO_INTERVAL
        self._pending_backrun: Optional[tuple] = None   # (w3, signed_tx, nonce)

    async def perform_sandwich(self) -> dict:
        _check_config()
        return await self._execute_real_sandwich()

    def start_auto(self, interval: int = 10) -> None:
        _check_config()
        self._auto_interval = interval
        self._auto_running  = True
        if self._auto_task is None or self._auto_task.done():
            self._auto_task = asyncio.create_task(self.auto_loop())
        logger.info("Auto attack started, interval=%ds", interval)

    def stop_auto(self) -> None:
        self._auto_running = False
        if self._auto_task and not self._auto_task.done():
            self._auto_task.cancel()

    def stop(self) -> None:
        self.stop_auto()

    @property
    def is_auto_running(self) -> bool:
        return self._auto_running

    async def _submit_backrun(self, w3, signed_tx, nonce) -> str:
        """Submit the delayed back‑run transaction."""
        from app.utils.web3_utils import send_raw_tx
        tx_hash = await send_raw_tx(w3, signed_tx)
        logger.info("BOT SELL (delayed): %s", tx_hash)
        return tx_hash

    async def _execute_real_sandwich(self) -> dict:
        from web3 import Web3
        from app.utils.web3_utils import (
            get_web3, load_account, build_and_sign_approve,
            build_and_sign_swap, send_raw_tx, get_nonce,
        )
        from app.models.database import store_transaction, store_event
        from app.api.ws import manager
        from app.core.detection import detection_engine, MemTx
        from app.core.mitigation import mitigation_engine

        w3 = get_web3()
        bot1     = load_account(settings.PRIVATE_KEY_BOT1)
        bot2     = load_account(settings.PRIVATE_KEY_BOT2)
        victim   = load_account(settings.PRIVATE_KEY_VICTIM)
        res_addr = Web3.to_checksum_address(settings.TOKEN_RES_ADDRESS)
        olv_addr = Web3.to_checksum_address(settings.TOKEN_OLV_ADDRESS)
        dex_addr = Web3.to_checksum_address(settings.DEX_CONTRACT_ADDRESS)

        AMT_BOT = Web3.to_wei(80, "ether")
        AMT_VIC = Web3.to_wei(30, "ether")
        t_start = time.time()
        logger.info("=== Real sandwich attack starting on %s ===",
                    "LOCAL ANVIL" if _is_local_testnet() else "SEPOLIA")

        # Nonces
        nonce_bot1   = await get_nonce(w3, bot1.address)
        nonce_victim = await get_nonce(w3, victim.address)
        nonce_bot2   = await get_nonce(w3, bot2.address)

        # Approvals
        s = await build_and_sign_approve(w3, bot1, res_addr, dex_addr, AMT_BOT, nonce_bot1)
        await send_raw_tx(w3, s); nonce_bot1 += 1

        s = await build_and_sign_approve(w3, victim, res_addr, dex_addr, AMT_VIC, nonce_victim)
        await send_raw_tx(w3, s); nonce_victim += 1

        # ----- 1. Bot1 BUY (front‑run) -----
        s_buy = await build_and_sign_swap(
            w3, bot1, res_addr, olv_addr, AMT_BOT, 0, nonce_bot1, "high")
        buy_hash = await send_raw_tx(w3, s_buy); nonce_bot1 += 1
        logger.info("BOT BUY: %s", buy_hash)

        buy_gas = _get_gas_price_for_priority("high")
        buy_payload = {
            "tx_hash": buy_hash, "sender": bot1.address,
            "token_in": "RES", "token_out": "OLV",
            "amount_in": float(Web3.from_wei(AMT_BOT, "ether")),
            "gas_price": buy_gas, "is_bot": True, "color": "orange",
            "etherscan_url": EXPLORER + buy_hash,
        }
        store_event("transaction_arrived", buy_payload)
        store_transaction({**buy_payload, "status": "submitted", "attack_id": None,
                           "bundle_id": None, "created_at": time.time()})
        await manager.broadcast({"type": "transaction_arrived", "data": buy_payload, "timestamp": time.time()})

        # ----- 2. Victim swap (built but NOT submitted yet) -----
        s_victim = await build_and_sign_swap(
            w3, victim, res_addr, olv_addr, AMT_VIC, 0, nonce_victim, "medium")
        vic_hash = w3.keccak(s_victim.rawTransaction).hex()
        nonce_victim += 1
        logger.info("VICTIM TX held for protection: %s", vic_hash)

        vic_gas = _get_gas_price_for_priority("medium")
        vic_payload = {
            "tx_hash": vic_hash, "sender": victim.address,
            "token_in": "RES", "token_out": "OLV",
            "amount_in": float(Web3.from_wei(AMT_VIC, "ether")),
            "gas_price": vic_gas, "is_bot": False, "color": "teal",
            "etherscan_url": EXPLORER + vic_hash,
        }
        store_event("transaction_arrived", vic_payload)
        store_transaction({**vic_payload, "status": "submitted", "attack_id": None,
                           "bundle_id": None, "created_at": time.time()})
        await manager.broadcast({"type": "transaction_arrived", "data": vic_payload, "timestamp": time.time()})

        # ----- 3. Bot2 SELL (built but NOT sent yet – will be sent after victim is settled) -----
        s_sell = await build_and_sign_swap(
            w3, bot2, olv_addr, res_addr, AMT_BOT, 0, nonce_bot2, "low")
        sell_gas = _get_gas_price_for_priority("low")
        sell_payload_built = {
            "tx_hash": None,  # will be filled after submission
            "sender": bot2.address,
            "token_in": "OLV", "token_out": "RES",
            "amount_in": float(Web3.from_wei(AMT_BOT, "ether")),
            "gas_price": sell_gas, "is_bot": True, "color": "orange",
            "etherscan_url": None,
        }

        # ----- 4. Feed all three into detection engine (bot2 sell is only simulated, not yet on chain) -----
        # We create a MemTx for the sell so detection can match the pattern.
        # The detection engine doesn't require the transaction to be already broadcast.
        for tx_hash, sender, gas_price, amount in [
            (buy_hash,  bot1.address,   buy_gas,  float(Web3.from_wei(AMT_BOT, "ether"))),
            (vic_hash,  victim.address, vic_gas,  float(Web3.from_wei(AMT_VIC, "ether"))),
            ("pending_sell", bot2.address, sell_gas, float(Web3.from_wei(AMT_BOT, "ether"))),
        ]:
            await detection_engine.process(MemTx(
                tx_hash=tx_hash, sender=sender,
                token_in="RES" if tx_hash != "pending_sell" else "OLV",
                token_out="OLV" if tx_hash != "pending_sell" else "RES",
                amount_in=amount, gas_price=gas_price,
                timestamp=time.time(),
                is_bot=(sender != victim.address),
            ))

        # ----- 5. Register victim raw tx for mitigation and wait for settlement -----
        mitigation_engine.store_pending_raw(vic_hash, s_victim.rawTransaction)

        # Wait for the mitigation engine to process the attack and submit the victim transaction.
        # We'll use a small sleep to give the engine time; in production we would wait for a callback.
        # For simplicity, wait 1 second – enough for the async mitigation to complete.
        await asyncio.sleep(1.2)

        # ----- 6. Now submit the back‑run transaction (after victim has been sent) -----
        sell_hash = await self._submit_backrun(w3, s_sell, nonce_bot2)
        nonce_bot2 += 1
        sell_payload_built["tx_hash"] = sell_hash
        sell_payload_built["etherscan_url"] = EXPLORER + sell_hash
        store_event("transaction_arrived", sell_payload_built)
        store_transaction({**sell_payload_built, "status": "submitted", "attack_id": None,
                           "bundle_id": None, "created_at": time.time()})
        await manager.broadcast({"type": "transaction_arrived", "data": sell_payload_built, "timestamp": time.time()})

        await asyncio.sleep(0.4)
        return {
            "status": "submitted",
            "buy_tx":    buy_hash,
            "victim_tx": vic_hash,
            "sell_tx":   sell_hash,
            "detection_ms": int((time.time() - t_start) * 1000),
            "explorer_buy":    EXPLORER + buy_hash,
            "explorer_sell":   EXPLORER + sell_hash,
        }

    async def auto_loop(self) -> None:
        while self._auto_running:
            try:
                await self.perform_sandwich()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Auto loop error: %s", e)
            await asyncio.sleep(self._auto_interval)


attack_simulator = AttackSimulator()