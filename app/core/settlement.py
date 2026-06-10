import logging
from app.core.mitigation import ProtectedBundle

logger = logging.getLogger(__name__)


class SettlementEngine:
    async def on_bundle_settled(self, bundle: ProtectedBundle, success: bool) -> None:
        if success:
            logger.info("Bundle %s settled", bundle.bundle_id)
        else:
            logger.warning("Bundle %s failed", bundle.bundle_id)


settlement_engine = SettlementEngine()
