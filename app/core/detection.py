import time, logging, asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Callable

logger = logging.getLogger(__name__)

WINDOW_SIZE = 80
TIME_WINDOW  = 30.0


@dataclass
class MemTx:
    tx_hash:   str
    sender:    str
    token_in:  str
    token_out: str
    amount_in: float
    gas_price: int
    timestamp: float
    is_bot:    bool = False


@dataclass
class SandwichAttack:
    attack_id:   str
    buy_tx:      MemTx
    victim_tx:   MemTx
    sell_tx:     MemTx
    confidence:  float
    detected_at: float = field(default_factory=time.time)


class DetectionEngine:
    def __init__(self):
        self._pool: deque = deque(maxlen=WINDOW_SIZE)
        self._seen: set   = set()
        self._listeners: List[Callable] = []

    def subscribe(self, listener: Callable) -> None:
        self._listeners.append(listener)

    async def process(self, tx: MemTx) -> Optional[SandwichAttack]:
        logger.debug("Processing tx: %s gas=%d is_bot=%s", tx.tx_hash[:8], tx.gas_price, tx.is_bot)
        self._pool.append(tx)
        return await self._detect()

    async def process_raw(self, tx_hash: str, sender: str,
                          calldata: str, gas_price: int) -> None:
        from app.utils.web3_utils import decode_swap_input
        decoded = decode_swap_input(calldata)
        if not decoded:
            return
        tx = MemTx(
            tx_hash=tx_hash, sender=sender,
            token_in=decoded["token_in"], token_out=decoded["token_out"],
            amount_in=decoded["amount_in"] / 1e18,
            gas_price=gas_price, timestamp=time.time(),
            is_bot=False,
        )
        await self.process(tx)

    async def _detect(self) -> Optional[SandwichAttack]:
        txs = list(self._pool)
        if len(txs) < 3:
            return None

        now = time.time()
        start = max(0, len(txs) - 20)   # only recent transactions
        for i in range(start, len(txs) - 2):
            buy    = txs[i]
            victim = txs[i + 1]
            sell   = txs[i + 2]

            if now - buy.timestamp > TIME_WINDOW:
                continue

            # Token direction must match (buy and victim swap the same pair)
            if buy.token_in != victim.token_in or buy.token_out != victim.token_out:
                logger.debug("Token mismatch: buy (%s->%s) vs victim (%s->%s)",
                             buy.token_in, buy.token_out, victim.token_in, victim.token_out)
                continue

            # Both buy and sell must be from bot accounts (front‑run and back‑run can be different bots)
            if not (buy.is_bot and sell.is_bot):
                logger.debug("Bot check failed: buy.is_bot=%s, sell.is_bot=%s", buy.is_bot, sell.is_bot)
                continue

            # Gas ordering: buy gas > victim gas > sell gas
            if not (buy.gas_price > victim.gas_price > sell.gas_price):
                logger.debug("Gas ordering failed: buy=%d victim=%d sell=%d",
                             buy.gas_price, victim.gas_price, sell.gas_price)
                continue

            key = f"{buy.tx_hash}:{victim.tx_hash}:{sell.tx_hash}"
            if key in self._seen:
                continue

            self._seen.add(key)
            import random, string
            aid = "att_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
            attack = SandwichAttack(
                attack_id=aid,
                buy_tx=buy, victim_tx=victim, sell_tx=sell,
                confidence=1.0, detected_at=time.time(),
            )
            logger.warning("SANDWICH DETECTED: %s victim=%s conf=1.0", aid, victim.tx_hash)
            for listener in self._listeners:
                asyncio.create_task(listener(attack))
            return attack

        return None


detection_engine = DetectionEngine()