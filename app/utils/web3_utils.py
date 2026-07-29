import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from functools import lru_cache

from web3 import Web3
from eth_account import Account
from eth_account.signers.local import LocalAccount

from app.config import settings

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=8)

ERC20_ABI = [
    {"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],
     "name":"approve","outputs":[{"type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"account","type":"address"}],
     "name":"balanceOf","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],
     "name":"transfer","outputs":[{"type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"from","type":"address"},{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],
     "name":"transferFrom","outputs":[{"type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"to","type":"address"},{"name":"amount","type":"uint256"}],
     "name":"mint","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"faucet","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[],"name":"decimals","outputs":[{"type":"uint8"}],"stateMutability":"view","type":"function"},
]

DEX_ABI = [
    {"inputs":[{"name":"tokenIn","type":"address"},{"name":"tokenOut","type":"address"},
               {"name":"amountIn","type":"uint256"},{"name":"minAmountOut","type":"uint256"}],
     "name":"swap","outputs":[{"name":"amountOut","type":"uint256"}],
     "stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"tokenA","type":"address"},{"name":"tokenB","type":"address"},
               {"name":"amountA","type":"uint256"},{"name":"amountB","type":"uint256"}],
     "name":"addLiquidity","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"tokenA","type":"address"},{"name":"tokenB","type":"address"}],
     "name":"createPair","outputs":[{"name":"","type":"bytes32"}],
     "stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"tokenIn","type":"address"},{"name":"tokenOut","type":"address"},
               {"name":"amountIn","type":"uint256"}],
     "name":"getAmountOut","outputs":[{"name":"","type":"uint256"}],
     "stateMutability":"view","type":"function"},
    {"inputs":[{"name":"tokenA","type":"address"},{"name":"tokenB","type":"address"}],
     "name":"getReserves","outputs":[{"name":"","type":"uint256"},{"name":"","type":"uint256"}],
     "stateMutability":"view","type":"function"},
]

SWAP_SELECTOR = Web3.keccak(text="swap(address,address,uint256,uint256)")[:4].hex()

CHAIN_SEPOLIA = 11155111
CHAIN_ANVIL = 31337


@lru_cache()
def get_web3() -> Web3:
    if not settings.SEPOLIA_RPC_URL:
        raise RuntimeError("SEPOLIA_RPC_URL not configured")

    url = settings.SEPOLIA_RPC_URL
    # For sending transactions, we only need HTTP – not WebSocket.
    if url.startswith("ws"):
        url = url.replace("ws://", "http://").replace("wss://", "https://")
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 30}))

    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to node at {url}")

    chain_id = w3.eth.chain_id
    logger.info("Web3 connected: chain_id=%s block=%s", chain_id, w3.eth.block_number)
    return w3


def get_dex(w3: Web3):
    return w3.eth.contract(
        address=Web3.to_checksum_address(settings.DEX_CONTRACT_ADDRESS),
        abi=DEX_ABI,
    )


def get_token(w3: Web3, address: str):
    return w3.eth.contract(
        address=Web3.to_checksum_address(address),
        abi=ERC20_ABI,
    )


def load_account(private_key: str) -> LocalAccount:
    if not private_key:
        raise ValueError("Private key not configured")
    return Account.from_key(private_key)


def get_gas_params(w3: Web3, priority: str = "medium") -> dict:
    chain_id = w3.eth.chain_id
    if chain_id in (CHAIN_ANVIL, 31337):
        gas_prices = {"high": 100, "medium": 50, "low": 20}
        price_wei = gas_prices.get(priority, 50) * 10**9
        return {"gasPrice": price_wei}

    try:
        latest = w3.eth.get_block("latest")
        base_fee = latest.get("baseFeePerGas", w3.eth.gas_price)
        multipliers = {"high": 2.0, "medium": 1.3, "low": 0.8}
        m = multipliers.get(priority, 1.3)
        max_fee = int(base_fee * m * 1.25)
        priority_fee = Web3.to_wei(1.5, "gwei")
        return {"maxFeePerGas": max_fee, "maxPriorityFeePerGas": priority_fee}
    except Exception:
        gas_price = w3.eth.gas_price
        multipliers = {"high": 2.0, "medium": 1.3, "low": 0.8}
        return {"gasPrice": int(gas_price * multipliers.get(priority, 1.3))}


async def run_in_executor(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, fn, *args)


async def send_raw_tx(w3: Web3, signed_tx) -> str:
    def _send():
        # NOTE: rawTransaction (camelCase) is correct for web3.py v6
        return w3.eth.send_raw_transaction(signed_tx.rawTransaction).hex()
    return await run_in_executor(_send)


async def wait_receipt(w3: Web3, tx_hash: str, timeout: int = 60) -> dict:
    def _wait():
        return dict(w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout))
    return await run_in_executor(_wait)


async def get_nonce(w3: Web3, address: str) -> int:
    def _get():
        return w3.eth.get_transaction_count(Web3.to_checksum_address(address))
    return await run_in_executor(_get)


def decode_swap_input(data: str) -> Optional[dict]:
    try:
        from eth_abi import decode
        raw = bytes.fromhex(data.replace("0x", ""))
        if raw[:4].hex() != SWAP_SELECTOR:
            return None
        token_in, token_out, amount_in, min_out = decode(
            ["address", "address", "uint256", "uint256"], raw[4:]
        )
        return {
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": amount_in,
            "min_out": min_out,
        }
    except Exception:
        return None


async def build_and_sign_approve(w3: Web3, account: LocalAccount, token_address: str,
                                  spender: str, amount: int, nonce: int) -> object:
    token = get_token(w3, token_address)
    gas_params = get_gas_params(w3, "medium")
    tx = token.functions.approve(
        Web3.to_checksum_address(spender), amount
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 80_000,
        "chainId": w3.eth.chain_id,
        **gas_params,
    })
    return account.sign_transaction(tx)


async def build_and_sign_swap(w3: Web3, account: LocalAccount, token_in: str,
                               token_out: str, amount_in: int, min_out: int,
                               nonce: int, gas_priority: str) -> object:
    dex = get_dex(w3)
    gas_params = get_gas_params(w3, gas_priority)
    tx = dex.functions.swap(
        Web3.to_checksum_address(token_in),
        Web3.to_checksum_address(token_out),
        amount_in,
        min_out,
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 220_000,
        "chainId": w3.eth.chain_id,
        **gas_params,
    })
    return account.sign_transaction(tx)