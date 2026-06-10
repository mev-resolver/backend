from pydantic_settings import BaseSettings
from functools import lru_cache
import sys, logging

logger = logging.getLogger(__name__)

REQUIRED = [
    "SEPOLIA_RPC_URL",
    "PRIVATE_KEY_BOT1",
    "PRIVATE_KEY_BOT2",
    "PRIVATE_KEY_VICTIM",
    "PRIVATE_KEY_RELAYER",
    "DEX_CONTRACT_ADDRESS",
    "TOKEN_RES_ADDRESS",
    "TOKEN_OLV_ADDRESS",
]

class Settings(BaseSettings):
    SEPOLIA_RPC_URL: str = ""
    PRIVATE_KEY_BOT1: str = ""
    PRIVATE_KEY_BOT2: str = ""
    PRIVATE_KEY_VICTIM: str = ""
    PRIVATE_KEY_RELAYER: str = ""
    DEX_CONTRACT_ADDRESS: str = ""
    TOKEN_RES_ADDRESS: str = ""
    TOKEN_OLV_ADDRESS: str = ""
    FLASHBOTS_RELAY_URL: str = "https://relay-sepolia.flashbots.net"
    ATTACK_AUTO_INTERVAL: int = 10
    PRICE_DRIFT_ENABLED: bool = True
    DATABASE_PATH: str = "/data/resolver.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CHAIN_ID: int = 11155111  # Sepolia

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def validate_required(self) -> list:
        missing = [k for k in REQUIRED if not getattr(self, k, "")]
        return missing

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
