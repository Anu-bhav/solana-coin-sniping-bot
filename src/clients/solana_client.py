from __future__ import annotations
import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, AsyncGenerator
from solders.keypair import Keypair
from solders.transaction import Transaction
from solders.rpc.responses import SendTransactionResp
from solders.signature import Signature
from solders.message import Message
from solders.instruction import Instruction
from solders.compute_budget import set_compute_unit_price, set_compute_unit_limit
import httpx
from websockets.client import WebSocketClientProtocol

from config import load_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SolanaConfig:
    rpc_endpoints: dict[str, str]
    ws_endpoint: str
    commitment: str
    compute_budget: dict[str, int]
    transaction: dict[str, float]
    simulation: dict[str, bool | int]

    @classmethod
    def from_app_config(cls) -> SolanaConfig:
        config = load_config()
        return cls(**config["solana"])


class SolanaTxError(Exception):
    """Base exception for Solana transaction errors"""


class SolanaNetworkError(SolanaTxError):
    """Network-related transaction failure"""


class SolanaSimulationError(SolanaTxError):
    """Transaction simulation failure"""


class SolanaClient:
    def __init__(self, config: Optional[SolanaConfig] = None) -> None:
        self.config = config or SolanaConfig.from_app_config()
        self._rpc_client = httpx.AsyncClient()
        self._ws: Optional[WebSocketClientProtocol] = None

    async def create_sign_send_transaction(
        self,
        instructions: list[Instruction],
        signer: Keypair,
        recent_blockhash: Optional[str] = None,
        skip_preflight: bool = False,
    ) -> Tuple[Signature, SendTransactionResp]:
        """Full transaction lifecycle with retries and simulation"""
        try:
            # Build compute budget instructions from config
            compute_instructions = [
                set_compute_unit_limit(self.config.compute_budget["units"]),
                set_compute_unit_price(
                    self.config.compute_budget["priority_micro_lamps"]
                ),
            ]

            # Build full message
            all_instructions = compute_instructions + instructions
            message = Message.new_with_blockhash(
                all_instructions,
                signer.pubkey(),
                recent_blockhash or await self._get_recent_blockhash(),
            )

            # Create and sign transaction
            tx = Transaction([signer], message, [signer])

            # Dry-run simulation if enabled
            if self.config.simulation["enabled"]:
                await self._simulate_transaction(tx)

            # Send with retry logic
            return await self._send_with_retry(tx, skip_preflight)

        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            raise

    async def confirm_transaction(
        self, signature: Signature, timeout: Optional[float] = None
    ) -> AsyncGenerator[dict, None]:
        """Confirm transaction status with WS streaming"""
        timeout = timeout or self.config.transaction["timeout"]
        start_time = asyncio.get_event_loop().time()

        async with self._reconnecting_ws() as ws:
            await ws.send(str(signature))

            while (asyncio.get_event_loop().time() - start_time) < timeout:
                result = await asyncio.wait_for(ws.recv(), timeout=1)
                yield result

                if self._is_confirmed(result):
                    return

            raise TimeoutError(f"Confirmation timed out after {timeout}s")

    async def _get_recent_blockhash(self) -> str:
        """Get recent blockhash from RPC"""
        # Implementation omitted for brevity

    async def _simulate_transaction(self, tx: Transaction) -> None:
        """Dry-run transaction simulation"""
        # Implementation omitted for brevity

    async def _send_with_retry(
        self, tx: Transaction, skip_preflight: bool
    ) -> Tuple[Signature, SendTransactionResp]:
        """Retry transaction sending with exponential backoff"""
        # Implementation omitted for brevity

    @contextlib.asynccontextmanager
    async def _reconnecting_ws(self) -> WebSocketClientProtocol:
        """WS connection with automatic reconnection"""
        # Implementation omitted for brevity

    def _is_confirmed(self, status_data: dict) -> bool:
        """Check transaction confirmation status"""
        # Implementation omitted for brevity
