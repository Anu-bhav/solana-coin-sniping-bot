import asyncio
import logging
import time
from typing import Any, List, Optional, Union, Callable

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.rpc.responses import (
    GetBalanceResp,
    GetAccountInfoResp,
    GetLatestBlockhashResp,
    GetTokenSupplyResp,
    GetTokenAccountBalanceResp,
    GetTransactionResp,
    SimulateTransactionResp,
    RpcResponseContext,
    SendTransactionResp,
    GetSignatureStatusesResp,
    RpcBlockhash,
    RpcTokenAccountBalance,
    RpcSupply,
    RpcSimulateTransactionResult,
)
from solders.transaction import (
    Transaction,  # Keep legacy Transaction
    TransactionError,
    VersionedTransaction,  # Add back VersionedTransaction
)
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

# from solders.message import Message # No longer needed for new_signed_with_payer
from solders.instruction import Instruction

from solana.rpc.async_api import AsyncClient  # Updated import path
from solana.rpc.commitment import Commitment, Confirmed, Finalized
from solana.rpc.core import RPCException
from solana.rpc.websocket_api import SolanaWsClientProtocol, connect

# Assuming logger is configured elsewhere and passed in
# from src.core.logger import log


class SolanaClient:
    """
    Asynchronous Solana client for interacting with the Solana blockchain.
    Handles RPC calls, transaction sending, and WebSocket subscriptions.
    """

    DEFAULT_COMMITMENT: Commitment = Confirmed
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY_S = 1

    def __init__(self, config: dict, logger: logging.Logger):
        """
        Initializes the SolanaClient.

        Args:
            config: Configuration dictionary containing Solana settings.
                    Expected keys: rpc_url, wss_url, private_key,
                                   transaction_timeout_s, retry_delay_s,
                                   priority_fee_micro_lamports, compute_units,
                                   dex_program_ids (list), monitored_program_ids (list).
            logger: Configured logger instance.
        """
        self.config = config
        self.logger = logger

        self.rpc_url = self.config["solana"]["rpc_url"]
        self.wss_url = self.config["solana"]["wss_url"]
        self.timeout = self.config["solana"].get("transaction_timeout_s", 30)
        self.retry_delay = self.config["solana"].get(
            "retry_delay_s", self.INITIAL_RETRY_DELAY_S
        )
        self.priority_fee = self.config["solana"].get(
            "priority_fee_micro_lamports", 1000
        )  # Default 1000 micro lamports
        self.compute_units = self.config["solana"].get(
            "compute_units", 200000
        )  # Default 200k CUs
        self.dex_program_ids = [
            Pubkey.from_string(pid)
            for pid in self.config["solana"].get("dex_program_ids", [])
        ]
        self.monitored_program_ids = [
            Pubkey.from_string(pid)
            for pid in self.config["solana"].get("monitored_program_ids", [])
        ]

        self.logger.info(
            f"Initializing SolanaClient with RPC: {self.rpc_url}, WSS: {self.wss_url}"
        )

        try:
            self.keypair = Keypair.from_base58_string(
                self.config["solana"]["private_key"]
            )
            self.logger.info(f"Loaded keypair for public key: {self.keypair.pubkey()}")
        except Exception as e:
            self.logger.exception(f"Failed to load keypair from private key: {e}")
            raise ValueError("Invalid private key provided in configuration.") from e

        # Initialize RPC client
        self.rpc_client = AsyncClient(
            self.rpc_url, commitment=self.DEFAULT_COMMITMENT, timeout=self.timeout
        )

        # Initialize WSS client state
        self.wss_connection: Optional[SolanaWsClientProtocol] = None
        self.log_subscription_task: Optional[asyncio.Task] = None
        self.log_callback: Optional[Callable] = None  # Callback for processing logs

        self.logger.info("SolanaClient initialized successfully.")

    async def close(self):
        """Closes the RPC and WSS connections."""
        self.logger.info("Closing SolanaClient connections...")
        await self.close_wss_connection()
        await self.rpc_client.close()
        self.logger.info("SolanaClient connections closed.")

    async def _make_rpc_call_with_retry(self, method: Callable, *args, **kwargs) -> Any:
        """
        Makes an RPC call with retry logic for transient errors.

        Args:
            method: The AsyncClient method to call.
            *args: Positional arguments for the method.
            **kwargs: Keyword arguments for the method.

        Returns:
            The result of the RPC call.

        Raises:
            RPCException: If the call fails after maximum retries.
        """
        retries = 0
        last_exception = None
        while retries < self.MAX_RETRIES:
            try:
                return await method(*args, **kwargs)
            except RPCException as e:
                last_exception = e
                # Check for specific transient errors like 429 Too Many Requests
                # Note: solana-py might wrap HTTP errors, need to inspect 'e'
                # For now, we retry on any RPCException
                self.logger.warning(
                    f"RPC call failed (attempt {retries + 1}/{self.MAX_RETRIES}): {e}. Retrying in {self.retry_delay * (2**retries)}s..."
                )
                await asyncio.sleep(self.retry_delay * (2**retries))
                retries += 1
            except asyncio.TimeoutError as e:
                last_exception = e
                self.logger.warning(
                    f"RPC call timed out (attempt {retries + 1}/{self.MAX_RETRIES}): {e}. Retrying in {self.retry_delay * (2**retries)}s..."
                )
                await asyncio.sleep(self.retry_delay * (2**retries))
                retries += 1
            except Exception as e:  # Catch other potential network issues
                last_exception = e
                self.logger.error(
                    f"Unexpected error during RPC call (attempt {retries + 1}/{self.MAX_RETRIES}): {e}. Retrying in {self.retry_delay * (2**retries)}s..."
                )
                await asyncio.sleep(self.retry_delay * (2**retries))
                retries += 1

        self.logger.error(f"RPC call failed after {self.MAX_RETRIES} retries.")
        if last_exception:
            raise last_exception
        else:
            # Should not happen if loop executed, but satisfy type checker
            raise RPCException(
                "RPC call failed after maximum retries without specific exception."
            )

    # --- RPC Wrapper Methods ---

    async def get_balance(
        self, pubkey: Pubkey, commitment: Optional[Commitment] = None
    ) -> GetBalanceResp:
        """Gets the SOL balance of a public key."""
        self.logger.debug(
            f"Getting balance for {pubkey} with commitment {commitment or self.DEFAULT_COMMITMENT}"
        )
        return await self._make_rpc_call_with_retry(
            self.rpc_client.get_balance,
            pubkey,
            commitment=commitment or self.DEFAULT_COMMITMENT,
        )

    async def get_account_info(
        self, pubkey: Pubkey, commitment: Optional[Commitment] = None
    ) -> GetAccountInfoResp:
        """Gets account information for a public key."""
        self.logger.debug(
            f"Getting account info for {pubkey} with commitment {commitment or self.DEFAULT_COMMITMENT}"
        )
        return await self._make_rpc_call_with_retry(
            self.rpc_client.get_account_info,
            pubkey,
            commitment=commitment or self.DEFAULT_COMMITMENT,
            encoding="base64",  # Or jsonParsed, depending on needs
        )

    async def get_latest_blockhash(
        self, commitment: Optional[Commitment] = None
    ) -> GetLatestBlockhashResp:
        """Gets the latest blockhash."""
        self.logger.debug(
            f"Getting latest blockhash with commitment {commitment or self.DEFAULT_COMMITMENT}"
        )
        return await self._make_rpc_call_with_retry(
            self.rpc_client.get_latest_blockhash,
            commitment=commitment or self.DEFAULT_COMMITMENT,
        )

    async def get_token_supply(
        self, mint_pubkey: Pubkey, commitment: Optional[Commitment] = None
    ) -> GetTokenSupplyResp:
        """Gets the total supply of a token mint."""
        self.logger.debug(
            f"Getting token supply for mint {mint_pubkey} with commitment {commitment or self.DEFAULT_COMMITMENT}"
        )
        return await self._make_rpc_call_with_retry(
            self.rpc_client.get_token_supply,
            mint_pubkey,
            commitment=commitment or self.DEFAULT_COMMITMENT,
        )

    async def get_token_account_balance(
        self, token_account_pubkey: Pubkey, commitment: Optional[Commitment] = None
    ) -> GetTokenAccountBalanceResp:
        """Gets the balance of a token account."""
        self.logger.debug(
            f"Getting token account balance for {token_account_pubkey} with commitment {commitment or self.DEFAULT_COMMITMENT}"
        )
        return await self._make_rpc_call_with_retry(
            self.rpc_client.get_token_account_balance,
            token_account_pubkey,
            commitment=commitment or self.DEFAULT_COMMITMENT,
        )

    async def get_parsed_transaction(
        self,
        tx_signature: str,
        commitment: Optional[Commitment] = Finalized,
        max_supported_transaction_version: int = 0,
    ) -> Optional[GetTransactionResp]:
        """Gets a parsed transaction by its signature."""
        self.logger.debug(
            f"Getting parsed transaction {tx_signature} with commitment {commitment}"
        )
        # Note: get_transaction returns Optional[GetTransactionResp] directly
        resp = await self._make_rpc_call_with_retry(
            self.rpc_client.get_transaction,
            tx_signature,
            commitment=commitment,
            encoding="jsonParsed",
            max_supported_transaction_version=max_supported_transaction_version,
        )
        return resp  # resp is already Optional[GetTransactionResp]

    # --- Transaction Methods ---

    def build_swap_instruction(
        self,
        dex_program_id: Pubkey,
        user_wallet: Pubkey,
        source_token_account: Pubkey,
        destination_token_account: Pubkey,
        source_mint: Pubkey,
        destination_mint: Pubkey,
        amount_in: int,
        min_amount_out: int,
        # Add other necessary params based on the specific DEX program (e.g., pool keys)
    ) -> Instruction:
        """
        Builds a swap instruction for a specific DEX.
        NOTE: This is a placeholder and needs implementation based on the target DEX program IDL.
        """
        self.logger.warning(
            f"Building swap instruction for DEX {dex_program_id} - Placeholder implementation!"
        )
        # Placeholder: Replace with actual instruction building logic
        # This will involve encoding data according to the DEX program's expected format.
        # Example using a hypothetical 'swap' instruction:
        # data = some_dex_layout.encode({ "amount_in": amount_in, "min_amount_out": min_amount_out })
        # keys = [
        #     AccountMeta(pubkey=user_wallet, is_signer=True, is_writable=False),
        #     AccountMeta(pubkey=source_token_account, is_signer=False, is_writable=True),
        #     AccountMeta(pubkey=destination_token_account, is_signer=False, is_writable=True),
        #     AccountMeta(pubkey=source_mint, is_signer=False, is_writable=False),
        #     AccountMeta(pubkey=destination_mint, is_signer=False, is_writable=False),
        #     # Add other accounts like pool state, authority, token program, etc.
        # ]
        # return Instruction(program_id=dex_program_id, data=b'', keys=[]) # Return empty instruction for now
        raise NotImplementedError("Swap instruction building is not yet implemented.")

    async def create_sign_send_transaction(
        self,
        instructions: List[Instruction],
        signers: Optional[List[Keypair]] = None,
        dry_run: bool = False,
        commitment: Commitment = Confirmed,
        skip_confirmation: bool = False,
    ) -> Union[SimulateTransactionResp, SendTransactionResp, str]:
        """
        Creates, signs, and sends a transaction with the given instructions.
        Includes Compute Budget instructions based on config.

        Args:
            instructions: List of instructions to include in the transaction.
            signers: Optional list of additional keypairs required to sign the transaction.
                     The client's main keypair is always included as the fee payer.
            dry_run: If True, simulate the transaction instead of sending.
            commitment: The commitment level to use for sending or simulating.
            skip_confirmation: If True and not a dry_run, returns the signature immediately
                               without waiting for confirmation.

        Returns:
            If dry_run is True: The simulation response (SimulateTransactionResp).
            If dry_run is False and skip_confirmation is True: The transaction signature (str).
            If dry_run is False and skip_confirmation is False: The send transaction response (SendTransactionResp)
                                                                after confirmation.
        """
        if signers is None:
            signers = []

        # Always include the client's keypair as the primary signer/fee payer
        all_signers = [self.keypair] + signers

        try:
            # 1. Get Latest Blockhash
            blockhash_resp = await self.get_latest_blockhash(commitment=commitment)
            recent_blockhash = blockhash_resp.value.blockhash

            # 2. Add Compute Budget Instructions
            compute_budget_instructions = [
                set_compute_unit_price(self.priority_fee),
                set_compute_unit_limit(self.compute_units),
            ]
            full_instructions = compute_budget_instructions + instructions
            # 3. Create and Sign Transaction using new_signed_with_payer
            # Positional args: instructions: List[Instruction], payer: Pubkey, signing_keypairs: List[Keypair], recent_blockhash: Hash
            tx = Transaction.new_signed_with_payer(
                full_instructions,  # Instructions list
                self.keypair.pubkey(),  # Payer's Pubkey
                all_signers,  # List of Keypair objects for signing (includes payer)
                recent_blockhash,
            )
            # No need for separate tx.sign or tx.sign_partial calls now

            self.logger.debug(
                f"Transaction created and signed by {len(all_signers)} signers."
            )

            # 4. Send or Simulate (Adjusted step number)
            if dry_run:
                self.logger.info("Dry running transaction...")
                # Simulate legacy Transaction directly
                simulation_resp = await self._make_rpc_call_with_retry(
                    self.rpc_client.simulate_transaction,
                    tx,  # Pass legacy tx directly
                    sig_verify=True,  # Verify signatures before simulating
                    commitment=commitment,
                )
                self.logger.info(
                    f"Transaction simulation result: Err={simulation_resp.value.err}, Logs={simulation_resp.value.logs}"
                )
                if simulation_resp.value.err:
                    self.logger.error(
                        f"Transaction simulation failed: {simulation_resp.value.err}"
                    )
                return simulation_resp
            else:
                self.logger.info("Sending transaction...")
                # Use send_raw_transaction if already serialized, or send_transaction
                # send_transaction handles serialization and signing again, which is redundant but simpler API
                # Let's serialize manually for clarity
                # Serialize legacy Transaction directly
                serialized_tx = tx.serialize()
                send_resp = await self._make_rpc_call_with_retry(
                    self.rpc_client.send_raw_transaction,
                    serialized_tx,  # Pass serialized legacy tx
                    opts={
                        "skip_preflight": False,
                        "preflight_commitment": commitment,
                    },  # Use opts for send_raw_transaction
                )
                signature = send_resp.value
                self.logger.info(f"Transaction sent with signature: {signature}")

                if skip_confirmation:
                    return str(signature)  # Return signature string directly

                # 7. Confirm Transaction (if not skipping)
                await self.confirm_transaction(str(signature), commitment=commitment)
                # Return the original SendTransactionResp which contains the signature
                return send_resp

        except RPCException as e:
            self.logger.exception(f"RPC error during transaction processing: {e}")
            raise
        except TransactionError as e:
            self.logger.exception(
                f"Transaction error during simulation or sending: {e}"
            )
            raise
        except Exception as e:
            self.logger.exception(
                f"Unexpected error during transaction processing: {e}"
            )
            raise

    async def confirm_transaction(
        self,
        signature: str,
        commitment: Commitment = Finalized,
        sleep_seconds: float = 2.0,
    ):
        """
        Confirms a transaction by polling its status.

        Args:
            signature: The transaction signature string.
            commitment: The commitment level to wait for.
            sleep_seconds: Time to wait between polling attempts.

        Raises:
            TimeoutError: If the transaction is not confirmed within the client's timeout.
            RPCException: If polling encounters an RPC error.
        """
        self.logger.info(
            f"Confirming transaction {signature} with commitment {commitment}..."
        )
        start_time = time.monotonic()
        while True:
            try:
                status_resp = await self._make_rpc_call_with_retry(
                    self.rpc_client.get_signature_statuses, [signature]
                )
                if status_resp.value and status_resp.value[0] is not None:
                    status = status_resp.value[0]
                    if status.err:
                        self.logger.error(
                            f"Transaction {signature} failed: {status.err}"
                        )
                        # Raise TransactionError with only the message string
                        raise TransactionError(f"Transaction failed confirmation: {status.err}")

                    current_commitment = status.confirmation_status
                    if current_commitment:
                        # Check if current commitment level meets or exceeds the desired level
                        commitment_order = [Confirmed, Finalized]  # Define order
                        desired_index = (
                            commitment_order.index(commitment)
                            if commitment in commitment_order
                            else -1
                        )
                        current_index = (
                            commitment_order.index(current_commitment)
                            if current_commitment in commitment_order
                            else -1
                        )

                        if current_index >= desired_index >= 0:
                            self.logger.info(
                                f"Transaction {signature} confirmed with status: {current_commitment}"
                            )
                            return True  # Confirmed

                    self.logger.debug(
                        f"Transaction {signature} status: {current_commitment or 'Processing'}. Waiting..."
                    )

                else:
                    # Status not yet available or RPC returned unexpected None
                    self.logger.debug(
                        f"Transaction {signature} status not yet available. Waiting..."
                    )

            except RPCException as e:
                self.logger.error(
                    f"RPC error while confirming transaction {signature}: {e}"
                )
                raise  # Propagate RPC errors

            # Check timeout
            if time.monotonic() - start_time > self.timeout:
                self.logger.error(
                    f"Timeout waiting for transaction {signature} confirmation."
                )
                raise asyncio.TimeoutError(
                    f"Timeout waiting for transaction {signature} confirmation."
                )

            await asyncio.sleep(sleep_seconds)

    # --- WebSocket Methods ---

    async def connect_wss(self):
        """Establishes a WebSocket connection."""
        if self.wss_connection and self.wss_connection.is_connected:
            self.logger.info("WebSocket connection already established.")
            return

        try:
            self.logger.info(f"Connecting to WebSocket: {self.wss_url}")
            # `connect` is an async generator yielding the protocol instance
            async for ws in connect(self.wss_url):
                self.wss_connection = ws
                self.logger.info("WebSocket connection established.")
                # Keep the connection alive by yielding control back to the event loop
                # The actual subscription logic will run concurrently
                # We break here because we just need the connection object
                break
            if not self.wss_connection:
                raise ConnectionError(
                    "Failed to establish WebSocket connection after connect() completed."
                )

        except Exception as e:
            self.logger.exception(f"Failed to connect to WebSocket: {e}")
            self.wss_connection = None
            raise ConnectionError(f"Failed to connect to WebSocket: {e}") from e

    async def _process_log_messages(self):
        """Internal task to process incoming log messages."""
        if not self.wss_connection or not self.wss_connection.is_connected:
            self.logger.error(
                "Cannot process log messages, WebSocket is not connected."
            )
            return

        try:
            async for msg in self.wss_connection:
                # Process the message (e.g., parse, filter, call callback)
                # self.logger.debug(f"Received WSS message: {msg}")
                if self.log_callback:
                    try:
                        # Assuming msg is a list containing subscription results
                        if isinstance(msg, list):
                            for item in msg:
                                if hasattr(item, "result") and hasattr(
                                    item.result, "value"
                                ):
                                    # This structure matches logs_subscribe results
                                    log_data = item.result.value
                                    # self.logger.debug(f"Processing log data: {log_data}")
                                    await self.log_callback(log_data)
                                else:
                                    self.logger.warning(
                                        f"Received unexpected WSS message format: {item}"
                                    )
                        else:
                            self.logger.warning(
                                f"Received unexpected WSS message type: {type(msg)}"
                            )

                    except Exception as e:
                        self.logger.exception(f"Error in log processing callback: {e}")
                else:
                    self.logger.warning("Log message received but no callback is set.")

        except asyncio.CancelledError:
            self.logger.info("Log processing task cancelled.")
        except Exception as e:
            self.logger.exception(f"Error in WebSocket message loop: {e}")
            # Attempt to reconnect or handle error appropriately
            await self.close_wss_connection()  # Close potentially broken connection

    async def start_log_subscription(
        self, callback: Callable, commitment: Commitment = Finalized
    ):
        """
        Starts subscribing to logs for monitored program IDs via WebSocket.

        Args:
            callback: An async function to call with each received log message value.
            commitment: The commitment level for the subscription.
        """
        if not self.wss_connection or not self.wss_connection.is_connected:
            await self.connect_wss()  # Ensure connection is established

        if not self.wss_connection:  # Check again after attempting connection
            self.logger.error("Cannot start log subscription, WSS connection failed.")
            return

        if self.log_subscription_task and not self.log_subscription_task.done():
            self.logger.warning(
                "Log subscription task already running. Stopping existing one."
            )
            await self.close_wss_connection()  # Close existing subscription and connection first
            await self.connect_wss()  # Reconnect
            if not self.wss_connection:
                self.logger.error(
                    "Cannot restart log subscription, WSS reconnection failed."
                )
                return

        self.log_callback = callback
        mentions = [str(pid) for pid in self.monitored_program_ids]
        self.logger.info(
            f"Starting log subscription for programs mentioned: {mentions} with commitment {commitment}"
        )

        try:
            # Start the subscription
            await self.wss_connection.logs_subscribe(
                mentions=mentions, commitment=commitment
            )
            self.logger.info("Successfully subscribed to logs.")

            # Start the background task to process messages
            self.log_subscription_task = asyncio.create_task(
                self._process_log_messages()
            )
            self.logger.info("Log processing task started.")

        except Exception as e:
            self.logger.exception(f"Failed to start log subscription: {e}")
            await self.close_wss_connection()  # Clean up connection if subscription fails

    async def close_wss_connection(self):
        """Closes the WebSocket connection and cancels the subscription task."""
        if self.log_subscription_task and not self.log_subscription_task.done():
            self.logger.info("Cancelling log subscription task...")
            self.log_subscription_task.cancel()
            try:
                await self.log_subscription_task
            except asyncio.CancelledError:
                self.logger.info("Log subscription task cancelled successfully.")
            except Exception as e:
                self.logger.exception(
                    f"Error during log subscription task cancellation: {e}"
                )
            self.log_subscription_task = None

        if self.wss_connection and self.wss_connection.is_connected:
            self.logger.info("Closing WebSocket connection...")
            try:
                # Unsubscribe if necessary - depends on how solana-py handles closure
                # await self.wss_connection.logs_unsubscribe(...) # Need subscription ID if applicable
                await self.wss_connection.close()
                self.logger.info("WebSocket connection closed.")
            except Exception as e:
                self.logger.exception(f"Error closing WebSocket connection: {e}")
        else:
            self.logger.debug("WebSocket connection already closed or not established.")

        self.wss_connection = None
        self.log_callback = None  # Clear callback on close
