import asyncio, random, time, logging
logger = logging.getLogger(__name__)

class PriceDriftService:
    def __init__(self):
        self.reserves = {"RES": 24_170.0, "OLV": 22_320.0}

    @property
    def price(self) -> float:
        return self.reserves["OLV"] / self.reserves["RES"]

    @property
    def tvl_usd(self) -> float:
        return self.reserves["RES"]*1.21 + self.reserves["OLV"]*1.47

    def get_output(self, token_in: str, amount_in: float) -> float:
        r_in  = self.reserves[token_in]
        r_out = self.reserves["OLV" if token_in=="RES" else "RES"]
        return (amount_in * r_out) / (r_in + amount_in) * 0.997

    def apply_swap(self, token_in: str, amount_in: float, amount_out: float) -> None:
        other = "OLV" if token_in=="RES" else "RES"
        self.reserves[token_in] += amount_in
        self.reserves[other]    -= amount_out

    async def run(self) -> None:
        from app.api.ws import manager
        while True:
            await asyncio.sleep(5)
            self.reserves["RES"] *= random.uniform(0.997, 1.003)
            self.reserves["OLV"] *= random.uniform(0.997, 1.003)
            await manager.broadcast({
                "type": "price_update",
                "data": {
                    "res_reserve": round(self.reserves["RES"],2),
                    "olv_reserve": round(self.reserves["OLV"],2),
                    "price":       round(self.price, 6),
                    "tvl_usd":     round(self.tvl_usd, 2),
                },
                "timestamp": time.time(),
            })

price_drift_service = PriceDriftService()
