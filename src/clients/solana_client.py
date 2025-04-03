import asyncio
import json
from typing import Optional, Dict, List
from solders.instruction import Instruction
from solders.keypair import Keypair
from solders.message import Message
from solders.transaction import Transaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.websocket_api import connect
from websockets import WebSocketClientProtocol
from ..exceptions import SolanaClientError
from ..config import settings


class SolanaClient:
    """Async client for Solana transaction management with devnet support."""

    def __init__(self) -> None:
        self.rpc_client = AsyncClient(settings.solana.rpc_url)
        self.ws_client: Optional[WebSocketClientProtocol] = None
        self.program_ids = settings.solana.program_ids
        self._validate_program_ids()

    def _validate_program_ids(self) -> None:
        """Verify configured program IDs match devnet addresses."""
        devnet_programs = {
            "system": "11111111111111111111111111111111",
            "token": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
            "associated_token": "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
        }

        for name, pid in self.program_ids.items():
            if devnet_programs.get(name) != pid:
                raise SolanaClientError(f"Invalid devnet program ID for {name}")

    async def create_sign_send_transaction(
        self,
        instructions: List[Instruction],
        signer: Keypair,
        skip_preflight: bool = False,
    ) -> str:
        """Create, simulate, and send a transaction with compute budget."""
        try:
            # Add compute budget instructions from config
            compute_units = settings.solana.compute_units
            compute_price = settings.solana.priority_fee
            priority_ix = Instruction(
                program_id=self.program_ids["system"],
                data=json.dumps(
                    {"compute_units": compute_units, "compute_price": compute_price}
                ).encode(),
                keys=[],
            )

            full_instructions = [priority_ix] + instructions

            # Build and sign transaction
            message = Message.new_with_blockhash(
                instructions=full_instructions,
                payer=signer.pubkey(),
                recent_blockhash=(
                    await self.rpc_client.get_recent_blockhash()
                ).value.blockhash,
            )
            tx = Transaction.populate(message, [signer])

            # Dry-run simulation
            sim_result = await self.rpc_client.simulate_transaction(tx)
            if sim_result.value.err:
                raise SolanaClientError(f"Simulation failed: {sim_result.value.logs}")

            # Send actual transaction
            tx_sig = (await self.rpc_client.send_transaction(tx)).value
            return str(tx_sig)

        except Exception as e:
            raise SolanaClientError(f"Transaction failed: {str(e)}") from e

    async def confirm_transaction(
        self, tx_sig: str, timeout: int = 60, confirmation_depth: int = 1
    ) -> bool:
        """Confirm transaction status via WebSocket."""
        try:
            self.ws_client = await connect(settings.solana.ws_url)
            await self.ws_client.program_subscribe(tx_sig, commitment="confirmed")

            async for msg in self.ws_client:
                if msg.result.context.slot >= confirmation_depth:
                    return True

                await asyncio.sleep(0.5)
                timeout -= 0.5
                if timeout <= 0:
                    raise TimeoutError("Confirmation timed out")

            return False
        finally:
            if self.ws_client:
                await self.ws_client.close()

    async def close(self) -> None:
        """Cleanup clients."""
        await self.rpc_client.close()
        if self.ws_client:
            await self.ws_client.close()
