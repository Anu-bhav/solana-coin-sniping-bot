import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from typing import List, Optional

# Assuming solders types are used based on service implementation
from solders.pubkey import Pubkey
from solders.rpc.responses import (
    RpcLogsResponse,
    LogsNotification,
    RpcResponseContext,
)

# Import specific error types from transaction_status based on user feedback
from solders.transaction_status import (
    EncodedTransactionWithStatusMeta,
    UiTransactionEncoding,
    UiTransactionStatusMeta,
    UiTransaction,
    UiMessage,
    UiInnerInstructions,
    InstructionErrorFieldless,  # Import specific error type
    TransactionErrorInstructionError,  # Import wrapper
)
from solders.transaction import TransactionError  # Keep base TransactionError
from solders.signature import Signature

# Import the class to test
from src.services.detection_service import DetectionService
from src.clients.solana_client import SolanaClient  # Needed for type hinting mocks
from src.database.manager import (
    DatabaseManager,
)

# --- Test Fixtures ---


@pytest.fixture
def mock_solana_client():
    """Fixture for a mocked SolanaClient."""
    client = AsyncMock(spec=SolanaClient)
    client.start_log_subscription = AsyncMock()
    client.get_parsed_transaction = AsyncMock()
    # Add unsubscribe mock if needed later
    # client.unsubscribe = AsyncMock()
    return client


@pytest.fixture
def mock_db_manager():
    """Fixture for a mocked DatabaseManager."""
    manager = AsyncMock(spec=DatabaseManager)
    manager.check_if_token_processed = AsyncMock(
        return_value=False
    )  # Default: not processed
    manager.add_detection = AsyncMock()
    return manager


@pytest.fixture
def mock_filter_queue():
    """Fixture for a mocked asyncio Queue."""
    queue = AsyncMock(spec=asyncio.Queue)
    queue.put = AsyncMock()
    return queue


@pytest.fixture
def test_config():
    """Fixture for a sample configuration dictionary."""
    return {
        "detection": {
            "program_ids": ["PROGRAM_ID_1", "PROGRAM_ID_2"],
            "target_base_mints": ["BASE_MINT_SOL", "BASE_MINT_USDC"],
            "reconnect_delay_seconds": 5,  # Use a short delay for testing
        },
        # Add other config sections if the service uses them
    }


@pytest.fixture
def detection_service(
    mock_solana_client, mock_db_manager, test_config, mock_filter_queue
):
    """Fixture to create a DetectionService instance with mocked dependencies."""
    return DetectionService(
        solana_client=mock_solana_client,
        db_manager=mock_db_manager,
        config=test_config,
        filter_queue=mock_filter_queue,
    )


# --- Helper Functions/Data ---


def create_mock_log_notification(
    signature: Signature, logs: List[str], err: Optional[TransactionError] = None
) -> LogsNotification:
    """Creates a mock LogsNotification object."""
    log_result = RpcLogsResponse(signature=signature, logs=logs, err=err)
    # Instantiate RpcResponseContext with slot only, assign value after
    context = RpcResponseContext(slot=1, api_version=None)
    context.value = log_result
    notification = LogsNotification(subscription=123, result=context)
    return notification


def create_mock_tx_details(
    signature: Signature,
    logs: Optional[List[str]] = None,
    fee_payer: Optional[Pubkey] = None,
    inner_instructions: Optional[List[UiInnerInstructions]] = None,
    # Add more fields as needed for parsing tests
) -> EncodedTransactionWithStatusMeta:
    """Creates a mock EncodedTransactionWithStatusMeta object."""
    if logs is None:
        logs = ["Log message 1", "Log message 2"]
    if fee_payer is None:
        fee_payer = Pubkey.new_unique()

    mock_meta = UiTransactionStatusMeta(
        err=None,
        fee=5000,
        pre_balances=[],
        post_balances=[],
        inner_instructions=inner_instructions,
        log_messages=logs,
        pre_token_balances=[],
        post_token_balances=[],
        rewards=[],
        loaded_addresses=None,
        compute_units_consumed=None,
        return_data=None,
    )
    # Revert UiMessage instantiation to use list of strings for account_keys
    mock_message = UiMessage(
        account_keys=[str(fee_payer), str(Pubkey.new_unique())],  # Use strings
        instructions=[],
        recent_blockhash=str(Signature.new_unique()),
        address_table_lookups=None,
    )
    mock_transaction = UiTransaction(signatures=[signature], message=mock_message)

    return EncodedTransactionWithStatusMeta(
        slot=12345,
        block_time=1678886400,
        transaction=mock_transaction,
        meta=mock_meta,
        version=0,
    )


# --- Test Class ---


@pytest.mark.asyncio  # Mark class to ensure all tests can use async fixtures
class TestDetectionService:

    # Mark test as async because it uses async fixtures
    async def test_initialization(
        self,
        detection_service,
        mock_solana_client,
        mock_db_manager,
        test_config,
        mock_filter_queue,
    ):
        """Verify service initializes attributes correctly."""
        assert detection_service.solana_client is mock_solana_client
        assert detection_service.db_manager is mock_db_manager
        assert detection_service.filter_queue is mock_filter_queue
        assert detection_service.program_ids == test_config["detection"]["program_ids"]
        assert (
            detection_service.target_base_mints
            == test_config["detection"]["target_base_mints"]
        )
        assert (
            detection_service.reconnect_delay
            == test_config["detection"]["reconnect_delay_seconds"]
        )
        assert not detection_service._running
        assert detection_service._subscription_id is None

    async def test_run_starts_subscription_and_stops(
        self, detection_service, mock_solana_client
    ):
        """Test that run() calls start_log_subscription and can be stopped."""
        mock_solana_client.start_log_subscription.side_effect = asyncio.Future()

        run_task = asyncio.create_task(detection_service.run())
        await asyncio.sleep(0.01)

        mock_solana_client.start_log_subscription.assert_called_once_with(
            program_ids=detection_service.program_ids,
            callback=detection_service._handle_log_message,
        )
        assert detection_service._running

        await detection_service.stop()
        await asyncio.sleep(0.01)

        assert not detection_service._running
        run_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass

    async def test_run_reconnects_on_error(
        self, detection_service, mock_solana_client, test_config
    ):
        """Test reconnection logic when start_log_subscription raises an error."""
        error_to_raise = ConnectionRefusedError("Test connection error")
        mock_solana_client.start_log_subscription.side_effect = [
            error_to_raise,
            asyncio.Future(),
        ]

        run_task = asyncio.create_task(detection_service.run())
        await asyncio.sleep(test_config["detection"]["reconnect_delay_seconds"] * 0.5)

        assert mock_solana_client.start_log_subscription.call_count == 1

        await asyncio.sleep(test_config["detection"]["reconnect_delay_seconds"] * 1.1)

        assert mock_solana_client.start_log_subscription.call_count == 2
        mock_solana_client.start_log_subscription.assert_called_with(
            program_ids=detection_service.program_ids,
            callback=detection_service._handle_log_message,
        )

        run_task.cancel()
        try:
            await run_task
        except asyncio.CancelledError:
            pass

    async def test_handle_log_message_confirmation(self, detection_service):
        """Test handling of subscription confirmation message (int ID)."""
        subscription_id = 98765
        await detection_service._handle_log_message(subscription_id)
        assert detection_service._subscription_id == subscription_id
        detection_service.solana_client.get_parsed_transaction.assert_not_called()
        detection_service.filter_queue.put.assert_not_called()

    async def test_handle_log_message_ignores_failed_tx(
        self, detection_service, mock_solana_client, mock_filter_queue
    ):
        """Test that logs from failed transactions are ignored."""
        sig = Signature.new_unique()
        # Correct AccountInUse mock
        mock_error = TransactionError(
            TransactionErrorInstructionError(0, InstructionErrorFieldless.AccountInUse)
        )
        mock_notification = create_mock_log_notification(sig, ["Log 1"], err=mock_error)

        await detection_service._handle_log_message(mock_notification)

        mock_solana_client.get_parsed_transaction.assert_not_called()
        mock_filter_queue.put.assert_not_called()

    async def test_handle_log_message_fetches_tx_details(
        self, detection_service, mock_solana_client
    ):
        """Test that transaction details are fetched for successful logs."""
        sig = Signature.new_unique()
        mock_notification = create_mock_log_notification(sig, ["Log 1"])
        mock_tx = create_mock_tx_details(sig)
        mock_solana_client.get_parsed_transaction.return_value = mock_tx

        with patch.object(
            detection_service, "_parse_transaction_for_pool", return_value=None
        ):
            await detection_service._handle_log_message(mock_notification)

        mock_solana_client.get_parsed_transaction.assert_awaited_once_with(
            sig,
            max_supported_transaction_version=0,
            encoding=UiTransactionEncoding.JsonParsed,
        )

    # --- Parsing and Filtering Tests (using placeholder parser) ---

    @pytest.fixture
    def mock_parsed_data(self, test_config):
        """Fixture for sample valid parsed data."""
        return {
            "token_mint": "NEW_TOKEN_MINT",
            "lp_address": "LP_ADDRESS_XYZ",
            "base_mint": test_config["detection"]["target_base_mints"][0],
            "creator_address": str(Pubkey.new_unique()),
        }

    async def test_handle_log_message_parsing_success_and_filter_pass(
        self,
        detection_service,
        mock_solana_client,
        mock_db_manager,
        mock_filter_queue,
        mock_parsed_data,
    ):
        """Test full flow when parsing succeeds and filters pass."""
        sig = Signature.new_unique()
        mock_notification = create_mock_log_notification(
            sig, ["Log indicating pool init"]
        )
        mock_tx = create_mock_tx_details(sig)

        mock_solana_client.get_parsed_transaction.return_value = mock_tx
        mock_db_manager.check_if_token_processed.return_value = False

        with patch.object(
            detection_service,
            "_parse_transaction_for_pool",
            return_value=mock_parsed_data,
        ):
            await detection_service._handle_log_message(mock_notification)

        detection_service._parse_transaction_for_pool.assert_called_once_with(
            mock_tx, mock_notification.result.value.logs
        )
        mock_db_manager.check_if_token_processed.assert_awaited_once_with(
            mock_parsed_data["token_mint"]
        )
        mock_filter_queue.put.assert_awaited_once_with(mock_parsed_data)
        mock_db_manager.add_detection.assert_awaited_once_with(
            token_mint=mock_parsed_data["token_mint"],
            lp_address=mock_parsed_data["lp_address"],
            base_mint=mock_parsed_data["base_mint"],
            creator_address=mock_parsed_data["creator_address"],
            tx_signature=str(sig),
            status="PENDING_FILTER",
        )

    async def test_handle_log_message_parsing_failure(
        self, detection_service, mock_solana_client, mock_filter_queue, mock_db_manager
    ):
        """Test flow when parsing returns None."""
        sig = Signature.new_unique()
        mock_notification = create_mock_log_notification(sig, ["Some logs"])
        mock_tx = create_mock_tx_details(sig)

        mock_solana_client.get_parsed_transaction.return_value = mock_tx

        with patch.object(
            detection_service, "_parse_transaction_for_pool", return_value=None
        ) as mock_parser:
            await detection_service._handle_log_message(mock_notification)

        mock_parser.assert_called_once()
        mock_db_manager.check_if_token_processed.assert_not_called()
        mock_filter_queue.put.assert_not_called()
        mock_db_manager.add_detection.assert_not_called()

    async def test_handle_log_message_filtering_base_mint_mismatch(
        self,
        detection_service,
        mock_solana_client,
        mock_filter_queue,
        mock_db_manager,
        mock_parsed_data,
    ):
        """Test filtering when base mint doesn't match target list."""
        sig = Signature.new_unique()
        mock_notification = create_mock_log_notification(
            sig, ["Log indicating pool init"]
        )
        mock_tx = create_mock_tx_details(sig)
        mock_solana_client.get_parsed_transaction.return_value = mock_tx

        invalid_parsed_data = mock_parsed_data.copy()
        invalid_parsed_data["base_mint"] = "NON_TARGET_BASE_MINT"

        with patch.object(
            detection_service,
            "_parse_transaction_for_pool",
            return_value=invalid_parsed_data,
        ):
            await detection_service._handle_log_message(mock_notification)

        detection_service._parse_transaction_for_pool.assert_called_once()
        mock_db_manager.check_if_token_processed.assert_not_called()
        mock_filter_queue.put.assert_not_called()
        mock_db_manager.add_detection.assert_not_called()

    async def test_handle_log_message_filtering_already_processed(
        self,
        detection_service,
        mock_solana_client,
        mock_filter_queue,
        mock_db_manager,
        mock_parsed_data,
    ):
        """Test filtering when token is already processed according to DB."""
        sig = Signature.new_unique()
        mock_notification = create_mock_log_notification(
            sig, ["Log indicating pool init"]
        )
        mock_tx = create_mock_tx_details(sig)
        mock_solana_client.get_parsed_transaction.return_value = mock_tx
        mock_db_manager.check_if_token_processed.return_value = True

        with patch.object(
            detection_service,
            "_parse_transaction_for_pool",
            return_value=mock_parsed_data,
        ):
            await detection_service._handle_log_message(mock_notification)

        detection_service._parse_transaction_for_pool.assert_called_once()
        mock_db_manager.check_if_token_processed.assert_awaited_once_with(
            mock_parsed_data["token_mint"]
        )
        mock_filter_queue.put.assert_not_called()
        mock_db_manager.add_detection.assert_not_called()

    # --- Error Handling Tests ---

    async def test_handle_log_message_handles_get_tx_error(
        self, detection_service, mock_solana_client, mock_filter_queue, mock_db_manager
    ):
        """Test error handling when get_parsed_transaction fails."""
        sig = Signature.new_unique()
        mock_notification = create_mock_log_notification(sig, ["Log 1"])
        mock_solana_client.get_parsed_transaction.side_effect = Exception(
            "Network Error"
        )

        await detection_service._handle_log_message(mock_notification)

        mock_filter_queue.put.assert_not_called()
        mock_db_manager.check_if_token_processed.assert_not_called()
        mock_db_manager.add_detection.assert_not_called()

    async def test_handle_log_message_handles_db_check_error(
        self,
        detection_service,
        mock_solana_client,
        mock_filter_queue,
        mock_db_manager,
        mock_parsed_data,
    ):
        """Test error handling when check_if_token_processed fails."""
        sig = Signature.new_unique()
        mock_notification = create_mock_log_notification(
            sig, ["Log indicating pool init"]
        )
        mock_tx = create_mock_tx_details(sig)
        mock_solana_client.get_parsed_transaction.return_value = mock_tx
        mock_db_manager.check_if_token_processed.side_effect = Exception(
            "DB Connection Error"
        )

        with patch.object(
            detection_service,
            "_parse_transaction_for_pool",
            return_value=mock_parsed_data,
        ):
            await detection_service._handle_log_message(mock_notification)

        mock_filter_queue.put.assert_not_called()
        mock_db_manager.add_detection.assert_not_called()

    async def test_handle_log_message_handles_db_add_error(
        self,
        detection_service,
        mock_solana_client,
        mock_db_manager,
        mock_filter_queue,
        mock_parsed_data,
    ):
        """Test that queueing still happens if add_detection fails."""
        sig = Signature.new_unique()
        mock_notification = create_mock_log_notification(
            sig, ["Log indicating pool init"]
        )
        mock_tx = create_mock_tx_details(sig)

        mock_solana_client.get_parsed_transaction.return_value = mock_tx
        mock_db_manager.check_if_token_processed.return_value = False
        mock_db_manager.add_detection.side_effect = Exception("DB Write Error")

        with patch.object(
            detection_service,
            "_parse_transaction_for_pool",
            return_value=mock_parsed_data,
        ):
            await detection_service._handle_log_message(mock_notification)

        mock_filter_queue.put.assert_awaited_once_with(mock_parsed_data)
        mock_db_manager.add_detection.assert_awaited_once()

    async def test_handle_log_message_handles_unexpected_message(
        self, detection_service, mock_filter_queue
    ):
        """Test handling of unexpected message types."""
        unexpected_message = {"some": "random", "data": "structure"}
        await detection_service._handle_log_message(unexpected_message)

        detection_service.solana_client.get_parsed_transaction.assert_not_called()
        mock_filter_queue.put.assert_not_called()
        detection_service.db_manager.add_detection.assert_not_called()

    # Test for _parse_transaction_for_pool (Placeholder version)
    # Mark as async because it uses async fixtures
    @pytest.mark.asyncio
    async def test_parse_transaction_for_pool_placeholder(
        self, detection_service, test_config
    ):
        """Test the placeholder parsing logic returns expected structure (or None)."""
        sig = Signature.new_unique()
        fee_payer = Pubkey.new_unique()
        logs_with_keyword = ["Program log: Instruction: Initialize", "other log"]
        tx_details_keyword = create_mock_tx_details(
            sig, logs=logs_with_keyword, fee_payer=fee_payer
        )
        parsed = detection_service._parse_transaction_for_pool(
            tx_details_keyword, logs_with_keyword
        )
        assert parsed is not None
        assert "token_mint" in parsed
        assert "lp_address" in parsed
        assert parsed["base_mint"] == test_config["detection"]["target_base_mints"][0]
        assert parsed["creator_address"] == str(fee_payer)

        logs_without_keyword = ["Program log: Some other instruction", "another log"]
        tx_details_no_keyword = create_mock_tx_details(sig, logs=logs_without_keyword)
        parsed = detection_service._parse_transaction_for_pool(
            tx_details_no_keyword, logs_without_keyword
        )
        assert parsed is None

        tx_details_no_logs = create_mock_tx_details(sig, logs=[])
        parsed = detection_service._parse_transaction_for_pool(tx_details_no_logs, [])
        assert parsed is None
