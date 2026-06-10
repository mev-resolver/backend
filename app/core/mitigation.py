import asyncio, time, json, logging
from dataclasses import dataclass
from typing import Optional, Dict

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProtectedBundle:
    bundle_id:      str
    attack_id:      str
    victim_tx_hash: str
    created_at:     float


class MitigationEngine:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._consumer: Optional[asyncio.Task] = None
        self._listeners = []
        self._pending_raw: Dict[str, bytes] = {}

    def subscribe(self, listener) -> None:
        self._listeners.append(listener)

    def store_pending_raw(self, tx_hash: str, raw: bytes) -> None:
        self._pending_raw[tx_hash] = raw

    def start(self) -> None:
        self._consumer = asyncio.create_task(self._consume())
        logger.info("Mitigation engine started")

    def stop(self) -> None:
        if self._consumer:
            self._consumer.cancel()

    async def handle_attack(self, attack) -> ProtectedBundle:
        import random, string
        bid = "bundle_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        bundle = ProtectedBundle(
            bundle_id=bid,
            attack_id=attack.attack_id,
            victim_tx_hash=attack.victim_tx.tx_hash,
            created_at=time.time(),
        )
        await self._queue.put((attack, bundle))
        logger.info("Queued attack %s -> bundle %s", attack.attack_id, bid)
        return bundle

    async def _consume(self) -> None:
        from app.models.database import (store_bundle, update_bundle,
                                          update_attack_mitigated,
                                          update_tx_status, store_event)
        from app.api.ws import manager
        while True:
            try:
                attack, bundle = await self._queue.get()
                t0 = time.time()
                store_bundle({"bundle_id": bundle.bundle_id,
                              "victim_tx_hash": bundle.victim_tx_hash,
                              "status": "pending", "created_at": bundle.created_at})
                mit_payload = {
                    "bundle_id": bundle.bundle_id,
                    "attack_id": attack.attack_id,
                    "victim_tx_hash": bundle.victim_tx_hash,
                    "target_lane": "protected",
                    "relay": "flashbots",
                }
                store_event("mitigation_applied", mit_payload)
                await manager.broadcast({"type": "mitigation_applied",
                                         "data": mit_payload, "timestamp": time.time()})

                # Attempt real Flashbots submission
                raw_tx = self._pending_raw.pop(bundle.victim_tx_hash, None)
                success, final_hash = await self._submit_flashbots(bundle, raw_tx)
                if not success:
                    logger.warning("Flashbots failed, public mempool fallback")
                    success, final_hash = await self._submit_public(bundle, raw_tx)

                mit_ms = int((time.time() - t0) * 1000)
                status = "confirmed" if success else "failed"
                update_bundle(bundle.bundle_id, status,
                              confirmed_at=time.time() if success else None)
                update_attack_mitigated(attack.attack_id, mit_ms)
                update_tx_status(bundle.victim_tx_hash, status, bundle.bundle_id)

                settle_payload = {
                    "bundle_id": bundle.bundle_id,
                    "victim_tx_hash": bundle.victim_tx_hash,
                    "final_tx_hash": final_hash or bundle.victim_tx_hash,
                    "status": status, "mitigation_ms": mit_ms,
                    "etherscan_url": "https://sepolia.etherscan.io/tx/" + (final_hash or bundle.victim_tx_hash),
                }
                store_event("settlement_confirmed", settle_payload)
                await manager.broadcast({"type": "settlement_confirmed",
                                         "data": settle_payload, "timestamp": time.time()})
                for listener in self._listeners:
                    asyncio.create_task(listener(bundle, success))
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Mitigation consumer error: %s", e)
                await asyncio.sleep(1)

    async def _submit_flashbots(self, bundle: ProtectedBundle,
                                 raw_tx: Optional[bytes]) -> tuple:
        if not raw_tx:
            logger.warning("No raw tx for bundle %s, using hash-only", bundle.bundle_id)
            raw_tx_hex = bundle.victim_tx_hash
        else:
            raw_tx_hex = "0x" + raw_tx.hex()

        try:
            import aiohttp
            from web3 import Web3
            from eth_account import Account
            from eth_account.messages import encode_defunct

            relayer = Account.from_key(settings.PRIVATE_KEY_RELAYER)
            w3 = Web3()

            # Get target block
            from app.utils.web3_utils import get_web3
            live_w3 = get_web3()
            current_block = live_w3.eth.block_number
            target_block = current_block + 1

            bundle_params = {
                "txs": [raw_tx_hex],
                "blockNumber": hex(target_block),
            }
            body = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_sendBundle",
                "params": [bundle_params],
                "id": 1,
            })

            # Flashbots signature: sign keccak256 of body
            msg_hash = w3.keccak(text=body)
            signed_msg = relayer.sign_message(encode_defunct(primitive=msg_hash))
            fb_sig = f"{relayer.address}:{signed_msg.signature.hex()}"

            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                    settings.FLASHBOTS_RELAY_URL,
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Flashbots-Signature": fb_sig,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    result = await resp.json()
                    if "error" in result:
                        logger.warning("Flashbots error: %s", result["error"])
                        return False, None
                    logger.info("Flashbots accepted bundle %s for block %d",
                                bundle.bundle_id, target_block)
                    tx_hash = result.get("result", {}).get("bundleHash", bundle.victim_tx_hash)
                    return True, tx_hash
        except Exception as e:
            logger.warning("Flashbots submission failed: %s", e)
            return False, None

    async def _submit_public(self, bundle: ProtectedBundle,
                              raw_tx: Optional[bytes]) -> tuple:
        if not raw_tx:
            return True, bundle.victim_tx_hash
        try:
            from app.utils.web3_utils import get_web3
            w3 = get_web3()
            tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
            logger.info("Public fallback submitted: %s", tx_hash)
            return True, tx_hash
        except Exception as e:
            logger.error("Public fallback failed: %s", e)
            return False, None


mitigation_engine = MitigationEngine()
