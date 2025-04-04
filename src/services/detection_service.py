import asyncio
import logging
from typing import Any, Dict, List, Optional

from solders.pubkey import Pubkey
from solders.rpc.responses import RpcLogsResponse, SubscriptionResult, LogsNotification
from solders.transaction_status import (
    EncodedTransactionWithStatusMeta,
    UiTransactionEncoding,
)
from solders.signature import Signature

from src.clients.solana_client import SolanaClient
from src.database.manager import DatabaseManager  # Corrected import path
from src.core.logger import get_logger  # Corrected import

# Assuming config is loaded elsewhere and passed as an object or dict
# from src.config import Config

# Configure logger for this service
logger = get_logger(__name__)  # Use get_logger instead of setup_logger


class DetectionService:
    """
    Listens to Solana logs for specified programs, detects new liquidity pools,
    performs initial filtering, and queues potential candidates for further processing.
    """

    def __init__(
        self,
        solana_client: SolanaClient,
        db_manager: DatabaseManager,
        config: Dict[str, Any],  # Or a specific Config object type
        filter_queue: asyncio.Queue,
    ):
        """
        Initializes the DetectionService.

        Args:
            solana_client: An instance of SolanaClient.
            db_manager: An instance of DatabaseManager.
            config: The application configuration dictionary or object.
            filter_queue: An asyncio Queue to send detected tokens for filtering.
        """
        self.solana_client = solana_client
        self.db_manager = db_manager
        self.filter_queue = filter_queue

        # Extract relevant configuration
        detection_config = config.get("detection", {})
        self.program_ids: List[str] = detection_config.get("program_ids", [])
        self.target_base_mints: List[str] = detection_config.get(
            "target_base_mints", []
        )
        self.reconnect_delay: int = detection_config.get("reconnect_delay_seconds", 60)

        if not self.program_ids:
            logger.warning("No program IDs configured for detection.")
        if not self.target_base_mints:
            logger.warning("No target base mints configured for detection.")

        self._running = False
        self._subscription_task: Optional[asyncio.Task] = None
        self._subscription_id: Optional[int] = (
            None  # Store the websocket subscription ID
        )

        logger.info("DetectionService initialized.")
        logger.info(f"Monitoring Program IDs: {self.program_ids}")
        logger.info(f"Target Base Mints: {self.target_base_mints}")

    async def run(self):
        """
        Starts the log subscription and handles reconnection.
        """
        self._running = True
        logger.info("Starting DetectionService run loop...")

        while self._running:
            self._subscription_id = (
                None  # Reset subscription ID on new connection attempt
            )
            try:
                logger.info(
                    f"Attempting to subscribe to logs for programs: {self.program_ids}"
                )
                # The callback will run indefinitely until the connection closes or an error occurs
                await self.solana_client.start_log_subscription(
                    program_ids=self.program_ids, callback=self._handle_log_message
                )
                # If start_log_subscription returns, the connection was likely closed
                logger.warning("Log subscription connection closed.")

            except asyncio.CancelledError:
                logger.info("DetectionService run loop cancelled.")
                self._running = False
                break  # Exit loop immediately if cancelled
            except Exception as e:
                logger.error(
                    f"Error during log subscription or in handler: {e}", exc_info=True
                )
                # Connection might be dead, wait before reconnecting

            if (
                self._running
            ):  # Avoid sleeping if stop() was called during exception handling
                logger.info(
                    f"Attempting to reconnect in {self.reconnect_delay} seconds..."
                )
                await asyncio.sleep(self.reconnect_delay)

        logger.info("DetectionService run loop finished.")

    async def stop(self):
        """
        Stops the detection service gracefully.
        """
        logger.info("Stopping DetectionService...")
        self._running = False  # Signal the run loop to stop

        # Attempt to unsubscribe if we have an active subscription ID
        if self._subscription_id is not None and hasattr(
            self.solana_client, "unsubscribe"
        ):
            try:
                logger.info(
                    f"Attempting to unsubscribe from log subscription ID: {self._subscription_id}"
                )
                # This depends on SolanaClient having an unsubscribe method
                await self.solana_client.unsubscribe(self._subscription_id)
                self._subscription_id = None
            except Exception as e:
                logger.error(f"Error during unsubscribe attempt: {e}", exc_info=True)

        # Cancel the main subscription task if it's running
        # Note: The subscription task might be managed within SolanaClient itself.
        # If SolanaClient.start_log_subscription blocks, we might not have a task handle here.
        # If it spawns a task internally, SolanaClient needs a method to stop it.
        # Assuming start_log_subscription blocks and handles its own cleanup on connection close.

        logger.info("DetectionService stopped.")

    async def _handle_log_message(
        self, message: Any
    ):  # Use Any for broader compatibility initially
        """
        Callback function to handle incoming log messages from the WebSocket.
        Processes log notifications, fetches transactions, parses for pools, filters, and queues.
        """
        # The structure of `message` depends heavily on the specific library (e.g., solana-py, solders)
        # Adapting based on common patterns and solders types mentioned in requirements
        try:
            # Type 1: Subscription Confirmation (often just the ID)
            if isinstance(message, int):
                self._subscription_id = message
                logger.info(
                    f"Successfully subscribed to logs. Subscription ID: {self._subscription_id}"
                )
                return  # Nothing more to do with confirmation

            # Type 2: Log Notification Data (using solders RpcLogsResponse structure as a guide)
            # Check if it matches the expected notification structure
            log_notification: Optional[LogsNotification] = None
            if isinstance(message, SubscriptionResult) and isinstance(
                message.result, LogsNotification
            ):
                log_notification = message.result
            elif isinstance(message, LogsNotification):  # Direct notification object
                log_notification = message
            # Add checks for other potential library-specific wrappers if needed

            if log_notification:
                log_details = log_notification.value
                signature = log_details.signature
                logs = log_details.logs
                err = log_details.err

                logger.debug(f"Received log notification for signature: {signature}")

                if err:
                    logger.debug(f"Transaction {signature} failed, ignoring: {err}")
                    return  # Ignore failed transactions

                # --- Fetch Transaction Details ---
                try:
                    logger.debug(f"Fetching transaction details for {signature}...")
                    tx_details: Optional[EncodedTransactionWithStatusMeta] = (
                        await self.solana_client.get_parsed_transaction(
                            signature,
                            max_supported_transaction_version=0,  # Request metadata
                            encoding=UiTransactionEncoding.JsonParsed,  # Request parsed format
                        )
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to fetch transaction details for {signature}: {e}",
                        exc_info=True,
                    )
                    return  # Cannot proceed without details

                if not tx_details:
                    logger.warning(
                        f"Could not find transaction details for {signature}"
                    )
                    return

                # --- Parse Transaction Logs/Instructions ---
                parsed_data = self._parse_transaction_for_pool(tx_details, logs)

                if not parsed_data:
                    # logger.debug(f"No relevant pool creation found in transaction {signature}")
                    return  # Not the transaction we are looking for

                logger.info(
                    f"Potential new pool detected in tx {signature}: {parsed_data}"
                )

                # --- Initial Filtering ---
                # 1. Check base mint
                if parsed_data["base_mint"] not in self.target_base_mints:
                    logger.info(
                        f"Ignoring token {parsed_data['token_mint']}: Base mint {parsed_data['base_mint']} not in target list {self.target_base_mints}."
                    )
                    return

                # 2. Check if already processed (using token mint as unique identifier)
                try:
                    is_processed = await self.db_manager.check_if_token_processed(
                        parsed_data["token_mint"]
                    )
                    if is_processed:
                        logger.info(
                            f"Ignoring token {parsed_data['token_mint']}: Already processed."
                        )
                        return
                except Exception as e:
                    logger.error(
                        f"Database error checking token {parsed_data['token_mint']}: {e}",
                        exc_info=True,
                    )
                    return  # Avoid queueing if DB check fails

                # --- Queueing ---
                logger.info(
                    f"Queueing token {parsed_data['token_mint']} (LP: {parsed_data['lp_address']}) for filtering."
                )
                await self.filter_queue.put(parsed_data)

                # --- Update Database ---
                try:
                    await self.db_manager.add_detection(
                        token_mint=parsed_data["token_mint"],
                        lp_address=parsed_data["lp_address"],
                        base_mint=parsed_data["base_mint"],
                        creator_address=parsed_data.get("creator_address"),  # Optional
                        tx_signature=str(signature),
                        status="PENDING_FILTER",
                    )
                    logger.debug(
                        f"Added detection record for {parsed_data['token_mint']} with status PENDING_FILTER."
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to add detection record for {parsed_data['token_mint']}: {e}",
                        exc_info=True,
                    )
                    # Continue even if DB update fails, as it's already queued

            else:
                logger.warning(
                    f"Received unexpected message type/structure from log subscription: {type(message)} | Content: {message}"
                )

        except Exception as e:
            # Catch-all for unexpected errors within the handler itself
            logger.error(f"Critical error in _handle_log_message: {e}", exc_info=True)

    def _parse_transaction_for_pool(
        self,
        tx_details: EncodedTransactionWithStatusMeta,
        direct_logs: List[str],  # Logs from the notification might be useful too
    ) -> Optional[Dict[str, str]]:
        """
        Parses transaction details to find pool initialization information.

        Args:
            tx_details: The detailed transaction information.
            direct_logs: Logs received directly in the notification.

        Returns:
            A dictionary containing 'token_mint', 'lp_address', 'base_mint',
            and optionally 'creator_address', or None if no pool creation is detected.

        **NOTE:** This implementation is a placeholder and needs to be adapted
        based on the specific logs/instructions emitted by the target DEX program
        (e.g., Raydium, Orca) during pool creation. You'll need to inspect
        actual transaction logs on an explorer (like Solscan or SolanaFM) for
        the target programs to determine the correct parsing logic.
        """
        # Placeholder Logic: Needs specific implementation based on target DEX logs
        # Example: Look for specific instruction names, log messages, or account keys.

        # Potential data sources within tx_details:
        # - tx_details.meta.log_messages: Combined logs (often includes CPI logs)
        # - tx_details.meta.inner_instructions: For CPI calls
        # - tx_details.transaction.message.instructions: Top-level instructions

        # --- Placeholder: Search log messages for keywords ---
        # This is a very basic and potentially unreliable method.
        # A more robust approach involves parsing instruction data or specific log formats.
        logs_to_check = tx_details.meta.log_messages if tx_details.meta else direct_logs
        if not logs_to_check:
            return None

        # Example keywords (replace with actual log patterns for Raydium/Orca etc.)
        # Raydium often involves instructions like 'initialize', 'initialize2' within its AMM program.
        # Orca uses different instruction names. Check their SDKs or transaction examples.
        # Look for logs indicating success and containing mint addresses.
        pool_init_keywords = [
            "initialize",
            "create_pool",
            "add_liquidity",
        ]  # Generic examples
        found_pool_init = any(
            keyword in log.lower()
            for keyword in pool_init_keywords
            for log in logs_to_check
        )

        if not found_pool_init:
            # logger.debug("No pool initialization keywords/patterns found in logs.")
            return None

        logger.debug(
            f"Potential pool initialization detected in logs for tx {tx_details.transaction.signatures[0]}. Needs specific parsing logic."
        )

        # --- Placeholder: Extract data (NEEDS ACTUAL IMPLEMENTATION) ---
        # This part requires inspecting actual transaction data for the target program.
        # You might need to:
        # 1. Identify the specific instruction (top-level or inner) responsible for pool creation.
        # 2. Check the program ID of that instruction matches the target DEX program ID.
        # 3. Parse the instruction data (if available and decoded) or associated logs.
        # 4. Extract account keys from the instruction (e.g., token A mint, token B mint, LP mint account).
        # 5. Look for specific log messages emitted by the program that contain the required addresses if not in accounts.

        # Example structure (replace with real extraction logic):
        try:
            # These are dummy values - replace with actual parsing logic
            # You would iterate through instructions/logs to find these based on patterns
            new_token_mint = (
                "PLACEHOLDER_TOKEN_MINT_"
                + str(tx_details.transaction.signatures[0])[:10]
            )
            base_token_mint = self.target_base_mints[
                0
            ]  # Assume first target base mint for placeholder
            lp_address = (
                "PLACEHOLDER_LP_ADDRESS_"
                + str(tx_details.transaction.signatures[0])[:10]
            )

            # Attempt to get the fee payer as a potential creator/deployer
            creator_address: Optional[str] = None
            # Ensure account_keys is not None and not empty before accessing
            account_keys = tx_details.transaction.message.account_keys
            if account_keys:
                # The first account key is typically the fee payer
                creator_address = str(account_keys[0])

            # *** Add Real Parsing Logic Here ***
            # Example: Find the 'Initialize' instruction for the target program ID.
            # Extract accounts[4] (TokenA), accounts[5] (TokenB), accounts[7] (Pool LP Mint) - indices vary!
            # Check logs for confirmation or specific data points.
            # If parsing fails to find real data, return None
            # if not real_data_found:
            #    logger.debug(f"Placeholder parsing used, but real data extraction needed for tx {tx_details.transaction.signatures[0]}.")
            #    return None # Or return placeholder if that's desired for testing

            # Basic validation
            if not all([new_token_mint, base_token_mint, lp_address]):
                logger.warning(
                    f"Failed to parse essential pool details from tx {tx_details.transaction.signatures[0]}"
                )
                return None

            return {
                "token_mint": new_token_mint,
                "lp_address": lp_address,
                "base_mint": base_token_mint,
                "creator_address": creator_address,
            }

        except Exception as e:
            logger.error(
                f"Error during parsing placeholder logic for tx {tx_details.transaction.signatures[0]}: {e}",
                exc_info=True,
            )
            return None
