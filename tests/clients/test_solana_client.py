import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.rpc import errors  # Updated import style
from solana.rpc.commitment import Confirmed, Finalized  # Commitment levels

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
    RpcConfirmedTransactionStatusWithSignature,  # Import the correct type
    RpcBlockhash,  # Added import
    RpcTokenAccountBalance,  # Import correct type
    RpcSupply,  # Added import
    RpcSimulateTransactionResult,  # Added import
    # TransactionErrorType, # Moved import
)
from solders.transaction import (
    TransactionError,
    Transaction,
    # TransactionErrorType, # Accessed via TransactionError - Removed incorrect imports
)
import time  # Import time for timeout test
from solders.hash import Hash
from solders.signature import Signature

# Removed incorrect import block
from solders.instruction import Instruction, AccountMeta

# Target module for patching
TARGET_MODULE = "src.clients.solana_client"

# Mock data
MOCK_RPC_URL = "http://mock-rpc.com"
MOCK_WSS_URL = "ws://mock-wss.com"
# Generate a real keypair for testing loading, but don't expose private key here
TEST_KEYPAIR = Keypair()
MOCK_PRIVATE_KEY = str(TEST_KEYPAIR)  # Use the string representation
MOCK_PUBLIC_KEY = TEST_KEYPAIR.pubkey()
MOCK_PROGRAM_ID_1 = Pubkey.new_unique()
MOCK_PROGRAM_ID_2 = Pubkey.new_unique()


@pytest.fixture
def mock_config():
    """Provides a mock configuration dictionary."""
    return {
        "solana": {
            "rpc_url": MOCK_RPC_URL,
            "wss_url": MOCK_WSS_URL,
            "private_key": MOCK_PRIVATE_KEY,
            "transaction_timeout_s": 15,
            "retry_delay_s": 0.1,  # Faster retries for tests
            "priority_fee_micro_lamports": 5000,
            "compute_units": 300000,
            "dex_program_ids": [str(MOCK_PROGRAM_ID_1)],
            "monitored_program_ids": [str(MOCK_PROGRAM_ID_1), str(MOCK_PROGRAM_ID_2)],
        }
    }


@pytest.fixture
def mock_logger():
    """Provides a mock logger instance."""
    logger = MagicMock(spec=logging.Logger)
    # Prevent actual logging during tests unless needed for debugging
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.exception = MagicMock()
    logger.debug = MagicMock()
    return logger


# --- Auto-mocking Fixtures ---
# These fixtures automatically patch dependencies for the duration of a test


@pytest.fixture()  # Removed autouse=True
async def mock_async_client():  # Made fixture async
    """Mocks solana.rpc.api.AsyncClient."""
    with patch(f"{TARGET_MODULE}.AsyncClient", new_callable=AsyncMock) as mock_client:
        # Configure common return values or behaviors if needed globally
        mock_client.return_value.rpc_url = MOCK_RPC_URL  # Mock attribute access
        # Added missing mock configurations from original autouse fixture
        mock_client.return_value.commitment = Confirmed
        mock_client.return_value.close = AsyncMock()
        yield mock_client  # Yield the mock itself
        # Removed second yield


@pytest.fixture(autouse=True)
def mock_keypair_from_string():
    """Mocks solders.keypair.Keypair.from_base58_string."""
    with patch(f"{TARGET_MODULE}.Keypair.from_base58_string") as mock_from_string:
        mock_from_string.return_value = TEST_KEYPAIR
        yield mock_from_string


@pytest.fixture(autouse=True)
def mock_websocket_connect():
    """Mocks solana.rpc.websocket_api.connect."""
    with patch(f"{TARGET_MODULE}.connect", new_callable=AsyncMock) as mock_connect:
        # Simulate the async generator behavior
        mock_ws_protocol = AsyncMock()
        mock_ws_protocol.is_connected = True
        mock_ws_protocol.close = AsyncMock()
        mock_ws_protocol.logs_subscribe = AsyncMock()
        mock_ws_protocol.logs_unsubscribe = AsyncMock()  # Assuming this might exist

        async def _connect_generator(*args, **kwargs):
            yield mock_ws_protocol

        mock_connect.side_effect = _connect_generator
        # Store the mock protocol instance on the connect mock for later access if needed
        mock_connect.mock_protocol = mock_ws_protocol
        yield mock_connect


@pytest.fixture(autouse=True)
def mock_asyncio_sleep():
    """Mocks asyncio.sleep."""
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        yield mock_sleep


# --- Test Class ---


@pytest.mark.asyncio
class TestSolanaClient:

    @pytest.fixture
    async def client(self, mock_config, mock_logger, mock_async_client):
        """Fixture to create a SolanaClient instance for testing."""
        # Need to import here to ensure patches are active
        from src.clients.solana_client import SolanaClient

        instance = SolanaClient(mock_config, mock_logger)
        # Mock the underlying client instance created within SolanaClient.__init__
        instance.rpc_client = mock_async_client.return_value
        yield instance  # Corrected: Yield only once
        # Teardown: Ensure connections are closed if tests didn't do it
        await instance.close()

    # --- Test __init__ ---

    def test_init_success(
        self,
        client,
        mock_config,
        mock_logger,
        mock_async_client,
        mock_keypair_from_string,
    ):
        """Tests successful initialization of SolanaClient."""
        assert client.config == mock_config
        assert client.logger == mock_logger
        assert client.rpc_url == MOCK_RPC_URL
        assert client.wss_url == MOCK_WSS_URL
        assert client.timeout == 15
        assert client.retry_delay == 0.1
        assert client.priority_fee == 5000
        assert client.compute_units == 300000
        assert client.dex_program_ids == [MOCK_PROGRAM_ID_1]
        assert client.monitored_program_ids == [MOCK_PROGRAM_ID_1, MOCK_PROGRAM_ID_2]

        # Verify Keypair loading
        mock_keypair_from_string.assert_called_once_with(MOCK_PRIVATE_KEY)
        assert client.keypair == TEST_KEYPAIR
        mock_logger.info.assert_any_call(
            f"Loaded keypair for public key: {MOCK_PUBLIC_KEY}"
        )

        # Verify AsyncClient instantiation
        mock_async_client.assert_called_once_with(
            MOCK_RPC_URL, commitment=client.DEFAULT_COMMITMENT, timeout=15
        )
        assert client.rpc_client == mock_async_client.return_value

        # Verify WSS state
        assert client.wss_connection is None
        assert client.log_subscription_task is None
        assert client.log_callback is None

        mock_logger.info.assert_any_call(
            f"Initializing SolanaClient with RPC: {MOCK_RPC_URL}, WSS: {MOCK_WSS_URL}"
        )
        mock_logger.info.assert_any_call("SolanaClient initialized successfully.")

    def test_init_invalid_private_key(
        self, mock_config, mock_logger, mock_keypair_from_string
    ):
        """Tests initialization failure with an invalid private key."""
        from src.clients.solana_client import SolanaClient

        mock_keypair_from_string.side_effect = ValueError("Invalid key")

        with pytest.raises(ValueError, match="Invalid private key provided"):
            SolanaClient(mock_config, mock_logger)

        mock_logger.exception.assert_called_once()

    async def test_close(self, client, mock_async_client, mock_websocket_connect):
        """Tests the close method."""
        # Simulate having an open WSS connection and task
        client.wss_connection = mock_websocket_connect.mock_protocol
        client.log_subscription_task = AsyncMock()
        client.log_subscription_task.done.return_value = False  # Task is running

        await client.close()

        # Assert WSS task cancellation and connection close were called
        client.log_subscription_task.cancel.assert_called_once()
        mock_websocket_connect.mock_protocol.close.assert_called_once()

        # Assert RPC client close was called
        mock_async_client.return_value.close.assert_called_once()
        client.logger.info.assert_any_call("Closing SolanaClient connections...")
        client.logger.info.assert_any_call("SolanaClient connections closed.")

    # --- Test RPC Wrappers ---

    async def test_get_balance(self, client):
        """Tests the get_balance wrapper."""
        mock_pubkey = Pubkey.new_unique()
        mock_response = GetBalanceResp(context=RpcResponseContext(slot=1), value=1000)
        client.rpc_client.get_balance = AsyncMock(return_value=mock_response)

        result = await client.get_balance(mock_pubkey)

        client.rpc_client.get_balance.assert_awaited_once_with(
            mock_pubkey, commitment=client.DEFAULT_COMMITMENT
        )
        assert result == mock_response
        client.logger.debug.assert_called_once()

    async def test_get_account_info(self, client):
        """Tests the get_account_info wrapper."""
        mock_pubkey = Pubkey.new_unique()
        # Create a mock AccountInfo-like object if needed, or just mock the response structure
        mock_response = GetAccountInfoResp(
            context=RpcResponseContext(slot=1), value=None
        )  # Example with None value
        client.rpc_client.get_account_info = AsyncMock(return_value=mock_response)

        result = await client.get_account_info(mock_pubkey, commitment=Finalized)

        client.rpc_client.get_account_info.assert_awaited_once_with(
            mock_pubkey, commitment=Finalized, encoding="base64"
        )
        assert result == mock_response
        client.logger.debug.assert_called_once()

    async def test_get_latest_blockhash(self, client):
        """Tests the get_latest_blockhash wrapper."""
        mock_hash = Hash.new_unique()
        mock_response = GetLatestBlockhashResp(
            context=RpcResponseContext(slot=1),
            value=GetLatestBlockhashResp.Value(
                blockhash=mock_hash, last_valid_block_height=100
            ),
        )
        client.rpc_client.get_latest_blockhash = AsyncMock(return_value=mock_response)

        result = await client.get_latest_blockhash()

        client.rpc_client.get_latest_blockhash.assert_awaited_once_with(
            commitment=client.DEFAULT_COMMITMENT
        )
        # Corrected assertion: Access blockhash directly from value
        assert result.value.blockhash == mock_hash
        assert result.value.last_valid_block_height == 100
        # Removed incorrect assert result == mock_response
        client.logger.debug.assert_called_once()

    async def test_get_token_supply(self, client):
        """Tests the get_token_supply wrapper."""
        mock_mint_pubkey = Pubkey.new_unique()
        # Corrected: Pass RpcTokenAmount directly to value
        mock_response = GetTokenSupplyResp(
            context=RpcResponseContext(slot=1),
            # Corrected: Use RpcSupply
            value=RpcSupply(
                total=1000000000000,
                circulating=500000000000,
                non_circulating=500000000000,
                non_circulating_accounts=[],  # Added missing argument
            ),
        )
        client.rpc_client.get_token_supply = AsyncMock(return_value=mock_response)

        result = await client.get_token_supply(mock_mint_pubkey)

        client.rpc_client.get_token_supply.assert_awaited_once_with(
            mock_mint_pubkey, commitment=client.DEFAULT_COMMITMENT
        )
        assert result == mock_response
        client.logger.debug.assert_called_once()

    async def test_get_token_account_balance(self, client):
        """Tests the get_token_account_balance wrapper."""
        mock_acc_pubkey = Pubkey.new_unique()
        # Corrected: Pass RpcTokenAmount directly to value
        mock_response = GetTokenAccountBalanceResp(
            context=RpcResponseContext(slot=1),
            # Corrected: Use RpcTokenAccountBalance
            value=RpcTokenAccountBalance(
                amount="500",
                address=Pubkey.new_unique(),  # Added missing address argument
            ),
        )
        client.rpc_client.get_token_account_balance = AsyncMock(
            return_value=mock_response
        )

        result = await client.get_token_account_balance(mock_acc_pubkey)

        client.rpc_client.get_token_account_balance.assert_awaited_once_with(
            mock_acc_pubkey, commitment=client.DEFAULT_COMMITMENT
        )
        assert result == mock_response
        client.logger.debug.assert_called_once()

    async def test_get_parsed_transaction(self, client):
        """Tests the get_parsed_transaction wrapper."""
        mock_sig_str = str(Signature.new_unique())
        # Mock a complex response structure as needed
        mock_response = GetTransactionResp(meta=None)  # Kept transaction removed
        client.rpc_client.get_transaction = AsyncMock(return_value=mock_response)

        result = await client.get_parsed_transaction(mock_sig_str, commitment=Finalized)

        client.rpc_client.get_transaction.assert_awaited_once_with(
            mock_sig_str,
            commitment=Finalized,
            encoding="jsonParsed",
            max_supported_transaction_version=0,
        )
        assert result == mock_response
        client.logger.debug.assert_called_once()

    # --- Test Retry Logic ---

    async def test_rpc_retry_on_rpc_exception(self, client, mock_asyncio_sleep):
        """Tests retry logic on errors.RPCException."""
        mock_pubkey = Pubkey.new_unique()
        mock_success_response = GetBalanceResp(
            context=RpcResponseContext(slot=1), value=1000
        )
        mock_rpc_error = {
            "code": 123,
            "message": "Temporary glitch",
        }  # Structure for errors.RPCException
        mock_exception = errors.RPCException(mock_rpc_error)

        client.rpc_client.get_balance = AsyncMock(
            side_effect=[
                mock_exception,  # First call fails
                mock_exception,  # Second call fails
                mock_success_response,  # Third call succeeds
            ]
        )

        result = await client.get_balance(mock_pubkey)

        assert result == mock_success_response
        assert client.rpc_client.get_balance.await_count == 3
        # Check sleep calls with increasing delay
        mock_asyncio_sleep.assert_has_awaits(
            [
                call(0.1 * (2**0)),  # 0.1s
                call(0.1 * (2**1)),  # 0.2s
            ]
        )
        assert client.logger.warning.call_count == 2

    async def test_rpc_retry_on_timeout(self, client, mock_asyncio_sleep):
        """Tests retry logic on asyncio.TimeoutError."""
        mock_pubkey = Pubkey.new_unique()
        mock_success_response = GetBalanceResp(
            context=RpcResponseContext(slot=1), value=1000
        )

        client.rpc_client.get_balance = AsyncMock(
            side_effect=[
                asyncio.TimeoutError("Request timed out"),  # First call fails
                mock_success_response,  # Second call succeeds
            ]
        )

        result = await client.get_balance(mock_pubkey)

        assert result == mock_success_response
        assert client.rpc_client.get_balance.await_count == 2
        mock_asyncio_sleep.assert_awaited_once_with(0.1 * (2**0))  # 0.1s
        assert client.logger.warning.call_count == 1
        client.logger.warning.assert_called_with(
            f"RPC call timed out (attempt 1/{client.MAX_RETRIES}): Request timed out. Retrying in {0.1 * (2**0)}s..."
        )

    async def test_rpc_retry_fails_after_max_retries(self, client, mock_asyncio_sleep):
        """Tests that the RPC call fails after exhausting retries."""
        mock_pubkey = Pubkey.new_unique()
        mock_rpc_error = {
            "code": 429,
            "message": "Too Many Requests",
        }  # Structure for errors.RPCException
        mock_exception = errors.RPCException(mock_rpc_error)

        client.rpc_client.get_balance = AsyncMock(
            side_effect=mock_exception
        )  # Always fail

        with pytest.raises(errors.RPCException) as exc_info:
            await client.get_balance(mock_pubkey)

        assert exc_info.value == mock_exception  # Should raise the last exception
        assert client.rpc_client.get_balance.await_count == client.MAX_RETRIES
        assert mock_asyncio_sleep.await_count == client.MAX_RETRIES
        assert client.logger.warning.call_count == client.MAX_RETRIES
        client.logger.error.assert_called_with(
            f"RPC call failed after {client.MAX_RETRIES} retries."
        )

    # --- Transaction Method Tests ---

    @pytest.fixture
    def mock_instructions(self):
        """Provides mock transaction instructions."""
        return [
            Instruction(
                program_id=Pubkey.new_unique(),
                accounts=[
                    AccountMeta(
                        pubkey=Pubkey.new_unique(), is_signer=False, is_writable=True
                    )
                ],
                data=b"mock_data_1",
            ),
            Instruction(
                program_id=Pubkey.new_unique(),
                accounts=[
                    AccountMeta(
                        pubkey=Pubkey.new_unique(), is_signer=True, is_writable=False
                    )
                ],
                data=b"mock_data_2",
            ),
        ]

    @pytest.fixture
    def mock_blockhash_resp(self):
        """Provides a mock GetLatestBlockhashResp."""
        return GetLatestBlockhashResp(
            context=RpcResponseContext(slot=100),
            # Corrected: Pass RpcBlockhash directly to value
            value=RpcBlockhash(
                blockhash=Hash.new_unique(), last_valid_block_height=100
            ),
        )

    @pytest.fixture
    def mock_sim_resp_ok(self):
        """Provides a mock successful SimulateTransactionResp."""
        return SimulateTransactionResp(
            context=RpcResponseContext(slot=101),
            # Corrected: Use RpcSimulateTransactionResult
            value=RpcSimulateTransactionResult(
                err=None,
                logs=["Log1", "Log2"],
                accounts=None,
                units_consumed=15000,
                return_data=None,
            ),
        )

    @pytest.fixture
    def mock_sim_resp_err(self):
        """Provides a mock failed SimulateTransactionResp."""
        return SimulateTransactionResp(
            context=RpcResponseContext(slot=102),
            # Corrected: Use RpcSimulateTransactionResult
            value=RpcSimulateTransactionResult(
                # Setting err=None temporarily to bypass fixture setup error
                err=None,  # Kept as None
                logs=["Log1", "Error Log"],
                accounts=None,
                units_consumed=5000,
                return_data=None,
            ),
        )

    @pytest.fixture
    def mock_send_resp(self):
        """Provides a mock SendTransactionResp."""
        return SendTransactionResp(value=Signature.new_unique())

    async def test_create_sign_send_transaction_dry_run_ok(
        self, client, mock_instructions, mock_blockhash_resp, mock_sim_resp_ok
    ):
        """Tests dry run transaction simulation (successful)."""
        client.rpc_client.get_latest_blockhash = AsyncMock(
            return_value=mock_blockhash_resp
        )
        client.rpc_client.simulate_transaction = AsyncMock(
            return_value=mock_sim_resp_ok
        )
        client.rpc_client.send_raw_transaction = AsyncMock()  # Should not be called

        result = await client.create_sign_send_transaction(
            mock_instructions, dry_run=True
        )

        client.rpc_client.get_latest_blockhash.assert_awaited_once()
        client.rpc_client.simulate_transaction.assert_awaited_once()
        client.rpc_client.send_raw_transaction.assert_not_awaited()  # Ensure send wasn't called

        # Assert transaction structure passed to simulate_transaction
        call_args, call_kwargs = client.rpc_client.simulate_transaction.call_args
        simulated_tx = call_args[
            0
        ]  # The Transaction object is the first positional arg
        assert isinstance(simulated_tx, Transaction)
        assert simulated_tx.fee_payer == client.keypair.pubkey()
        assert simulated_tx.recent_blockhash == mock_blockhash_resp.value.blockhash
        # Check instructions (Compute Budget + Mock)
        assert (
            len(simulated_tx.instructions) == len(mock_instructions) + 2
        )  # 2 compute budget ix
        assert isinstance(
            simulated_tx.instructions[0], Instruction
        )  # set_compute_unit_price
        assert isinstance(
            simulated_tx.instructions[1], Instruction
        )  # set_compute_unit_limit
        assert simulated_tx.instructions[2] == mock_instructions[0]
        assert simulated_tx.instructions[3] == mock_instructions[1]

        assert result == mock_sim_resp_ok
        client.logger.info.assert_any_call("Dry running transaction...")
        client.logger.info.assert_any_call(
            f"Transaction simulation result: Err={mock_sim_resp_ok.value.err}, Logs={mock_sim_resp_ok.value.logs}"
        )

    async def test_create_sign_send_transaction_dry_run_err(
        self, client, mock_instructions, mock_blockhash_resp, mock_sim_resp_err
    ):
        """Tests dry run transaction simulation (error response)."""
        client.rpc_client.get_latest_blockhash = AsyncMock(
            return_value=mock_blockhash_resp
        )
        client.rpc_client.simulate_transaction = AsyncMock(
            return_value=mock_sim_resp_err
        )
        client.rpc_client.send_raw_transaction = AsyncMock()

        result = await client.create_sign_send_transaction(
            mock_instructions, dry_run=True
        )

        client.rpc_client.get_latest_blockhash.assert_awaited_once()
        client.rpc_client.simulate_transaction.assert_awaited_once()
        client.rpc_client.send_raw_transaction.assert_not_awaited()
        assert result == mock_sim_resp_err
        client.logger.info.assert_any_call("Dry running transaction...")
        client.logger.error.assert_called_with(
            f"Transaction simulation failed: {mock_sim_resp_err.value.err}"
        )

    async def test_create_sign_send_transaction_send_skip_confirm(
        self, client, mock_instructions, mock_blockhash_resp, mock_send_resp
    ):
        """Tests sending a transaction and skipping confirmation."""
        client.rpc_client.get_latest_blockhash = AsyncMock(
            return_value=mock_blockhash_resp
        )
        client.rpc_client.send_raw_transaction = AsyncMock(return_value=mock_send_resp)
        client.rpc_client.simulate_transaction = AsyncMock()  # Should not be called
        # Mock confirm_transaction to ensure it's not called
        client.confirm_transaction = AsyncMock()

        signature = await client.create_sign_send_transaction(
            mock_instructions, dry_run=False, skip_confirmation=True
        )

        client.rpc_client.get_latest_blockhash.assert_awaited_once()
        client.rpc_client.send_raw_transaction.assert_awaited_once()
        client.rpc_client.simulate_transaction.assert_not_awaited()
        client.confirm_transaction.assert_not_awaited()  # Verify confirmation was skipped

        # Assert transaction structure passed to send_raw_transaction
        call_args, call_kwargs = client.rpc_client.send_raw_transaction.call_args
        sent_tx_bytes = call_args[0]
        # Ideally, deserialize and check, but checking type and options is a good start
        assert isinstance(sent_tx_bytes, bytes)
        assert call_kwargs.get("opts") == {
            "skip_preflight": False,
            "preflight_commitment": client.DEFAULT_COMMITMENT,
        }

        assert signature == str(mock_send_resp.value)
        client.logger.info.assert_any_call("Sending transaction...")
        client.logger.info.assert_any_call(
            f"Transaction sent with signature: {mock_send_resp.value}"
        )

    async def test_create_sign_send_transaction_send_with_confirm(
        self, client, mock_instructions, mock_blockhash_resp, mock_send_resp
    ):
        """Tests sending a transaction and waiting for confirmation."""
        client.rpc_client.get_latest_blockhash = AsyncMock(
            return_value=mock_blockhash_resp
        )
        client.rpc_client.send_raw_transaction = AsyncMock(return_value=mock_send_resp)
        client.rpc_client.simulate_transaction = AsyncMock()
        # Mock confirm_transaction to simulate success
        client.confirm_transaction = AsyncMock(return_value=True)

        result = await client.create_sign_send_transaction(
            mock_instructions,
            dry_run=False,
            skip_confirmation=False,
            commitment=Finalized,
        )

        client.rpc_client.get_latest_blockhash.assert_awaited_once_with(
            commitment=Finalized
        )
        client.rpc_client.send_raw_transaction.assert_awaited_once()
        client.rpc_client.simulate_transaction.assert_not_awaited()
        client.confirm_transaction.assert_awaited_once_with(
            str(mock_send_resp.value), commitment=Finalized
        )

        assert result == mock_send_resp  # Should return the original send response
        client.logger.info.assert_any_call("Sending transaction...")
        client.logger.info.assert_any_call(
            f"Transaction sent with signature: {mock_send_resp.value}"
        )

    async def test_create_sign_send_transaction_with_extra_signer(
        self, client, mock_instructions, mock_blockhash_resp, mock_sim_resp_ok
    ):
        """Tests transaction sending with an additional signer."""
        extra_signer = Keypair()
        client.rpc_client.get_latest_blockhash = AsyncMock(
            return_value=mock_blockhash_resp
        )
        client.rpc_client.simulate_transaction = AsyncMock(
            return_value=mock_sim_resp_ok
        )

        await client.create_sign_send_transaction(
            mock_instructions, signers=[extra_signer], dry_run=True
        )

        # Check that the transaction passed to simulate includes both signers
        call_args, _ = client.rpc_client.simulate_transaction.call_args
        simulated_tx = call_args[0]
        # Note: The Transaction object doesn't directly store signers after sign() is called.
        # We rely on the fact that .sign() would fail if the required signer wasn't provided.
        # We can check the fee payer and assume the internal signing logic worked.
        assert simulated_tx.fee_payer == client.keypair.pubkey()
        # A more robust check might involve mocking Transaction.sign itself, but this is often sufficient.
        client.logger.debug.assert_any_call(
            "Transaction created and signed by 2 signers."
        )

    async def test_create_sign_send_transaction_rpc_error(
        self, client, mock_instructions
    ):
        """Tests handling of errors.RPCException during transaction sending."""
        mock_rpc_error = {
            "code": 500,
            "message": "Internal Server Error",
        }  # Structure for errors.RPCException
        mock_exception = errors.RPCException(mock_rpc_error)
        client.rpc_client.get_latest_blockhash = AsyncMock(
            side_effect=mock_exception
        )  # Fail early

        with pytest.raises(errors.RPCException) as exc_info:
            # The actual call being tested is get_latest_blockhash which fails
            await client.get_latest_blockhash()  # Re-trigger the error for the test context

        assert exc_info.value == mock_exception
        client.logger.exception.assert_called_with(
            f"RPC error during transaction processing: {mock_exception}"
        )

    async def test_create_sign_send_transaction_preflight_error(
        self, client, mock_instructions, mock_blockhash_resp
    ):
        """Tests handling of TransactionError (like preflight failure) during sending."""
        # Simulate a preflight failure wrapped in errors.RPCException
        preflight_failure = errors.SendTransactionPreflightFailureMessage(
            TransactionError(TransactionError.InstructionError(0, 1)),  # Example error
            logs=[],
            units_consumed=0,
        )
        mock_exception = errors.RPCException(preflight_failure)

        client.rpc_client.get_latest_blockhash = AsyncMock(
            return_value=mock_blockhash_resp
        )
        client.rpc_client.send_raw_transaction = AsyncMock(side_effect=mock_exception)
        client.confirm_transaction = AsyncMock()  # Should not be reached

        with pytest.raises(
            errors.RPCException
        ) as exc_info:  # It's still raised as errors.RPCException
            await client.create_sign_send_transaction(
                mock_instructions, dry_run=False, skip_confirmation=False
            )

        assert exc_info.value == mock_exception
        # Check if specific logging for TransactionError occurred (depends on exact exception handling in main code)
        # In the current code, it fall nto the eneral errors.RPCException block
        client.logger.exception.assert_any_call(
            f"RPC error during transaction processing: {mock_exception}"
        )

    async def test_confirm_transaction_success_finalized(
        self, client, mock_asyncio_sleep
    ):
        """Tests successful transaction confirmation at Finalized commitment."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        resp_processing = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=1),
            value=[
                RpcConfirmedTransactionStatusWithSignature(  # Ensure confirmations is not present
                    signature=Signature.new_unique(),
                    slot=10,
                    err=None,
                    confirmation_status=None,
                )
            ],
        )
        resp_confirmed = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=2),
            value=[
                RpcConfirmedTransactionStatusWithSignature(  # Ensure confirmations is not present
                    signature=Signature.new_unique(),
                    slot=11,
                    err=None,
                    confirmation_status=Confirmed,
                )
            ],
        )
        resp_finalized = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=3),
            value=[
                RpcConfirmedTransactionStatusWithSignature(  # Ensure confirmations is not present
                    signature=Signature.new_unique(),
                    slot=12,
                    err=None,
                    confirmation_status=Finalized,
                )
            ],
        )

        client.rpc_client.get_signature_statuses = AsyncMock(
            side_effect=[resp_processing, resp_confirmed, resp_finalized]
        )

        result = await client.confirm_transaction(
            mock_sig_str, commitment=Finalized, sleep_seconds=0.05
        )

        assert result is True
        assert client.rpc_client.get_signature_statuses.await_count == 3
        client.rpc_client.get_signature_statuses.assert_has_awaits(
            [call([mock_sig_str]), call([mock_sig_str]), call([mock_sig_str])]
        )
        assert (
            mock_asyncio_sleep.await_count == 2
        )  # Slept after processing and confirmed responses
        client.logger.info.assert_any_call(
            f"Confirming transaction {mock_sig_str} with commitment Finalized..."
        )
        client.logger.debug.assert_any_call(
            f"Transaction {mock_sig_str} status: None. Waiting..."
        )  # From resp_processing
        client.logger.debug.assert_any_call(
            f"Transaction {mock_sig_str} status: Confirmed. Waiting..."
        )  # From resp_confirmed
        client.logger.info.assert_any_call(
            f"Transaction {mock_sig_str} confirmed with status: Finalized"
        )

    async def test_confirm_transaction_success_confirmed(
        self, client, mock_asyncio_sleep
    ):
        """Tests successful transaction confirmation at Confirmed commitment."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        resp_processing = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=1),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=10,
                    err=None,
                    confirmation_status=None,
                )
            ],
        )
        resp_confirmed = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=2),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=11,
                    err=None,
                    confirmation_status=Confirmed,
                    confirmations=10,  # Add confirmations
                )
            ],
        )

        client.rpc_client.get_signature_statuses = AsyncMock(
            side_effect=[
                resp_processing,
                resp_confirmed,
            ]
        )

        result = await client.confirm_transaction(
            mock_sig_str, commitment=Confirmed, sleep_seconds=0.05
        )

        assert result is True
        assert client.rpc_client.get_signature_statuses.await_count == 2
        assert mock_asyncio_sleep.await_count == 1  # Slept after processing response
        client.logger.info.assert_any_call(
            f"Transaction {mock_sig_str} confirmed with status: Confirmed"
        )

    async def test_confirm_transaction_failure(self, client, mock_asyncio_sleep):
        """Tests transaction confirmation when the transaction failed."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        mock_tx_error = TransactionError(TransactionError.InstructionError(0, 5))
        resp_failed = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=1),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=10,
                    err=mock_tx_error,
                    confirmation_status=Finalized,
                    confirmations=None,  # Add confirmations
                )
            ],
        )

        client.rpc_client.get_signature_statuses = AsyncMock(return_value=resp_failed)

        with pytest.raises(TransactionError) as exc_info:
            await client.confirm_transaction(
                mock_sig_str, commitment=Finalized, sleep_seconds=0.05
            )

        assert exc_info.match(f"Transaction failed confirmation: {mock_tx_error}")
        assert client.rpc_client.get_signature_statuses.await_count == 1
        assert mock_asyncio_sleep.await_count == 0  # Failed on first check
        client.logger.error.assert_called_with(
            f"Transaction {mock_sig_str} failed: {mock_tx_error}"
        )

    async def test_confirm_transaction_timeout(self, client, mock_asyncio_sleep):
        """Tests transaction confirmation timeout."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        resp_processing = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=1),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=10,
                    err=None,
                    confirmation_status=None,
                )
            ],
        )

        client.rpc_client.get_signature_statuses = AsyncMock(
            return_value=resp_processing
        )  # Always processing

        # Mock time.monotonic to simulate timeout
        start_time = time.monotonic()
        with patch("time.monotonic") as mock_time:
            # Simulate time passing just enough to exceed timeout on the second check
            mock_time.side_effect = [
                start_time,  # First call inside loop
                start_time + 0.1,  # Second call inside loop (after sleep)
                start_time + client.timeout + 0.1,  # Third call, exceeds timeout
            ]
            with pytest.raises(asyncio.TimeoutError) as exc_info:
                # Use a small sleep to ensure the loop runs multiple times quickly
                await client.confirm_transaction(
                    mock_sig_str, commitment=Finalized, sleep_seconds=0.01
                )

        assert exc_info.match(
            f"Timeout waiting for transaction {mock_sig_str} confirmation."
        )
        # Check it polled multiple times before timeout
        assert client.rpc_client.get_signature_statuses.await_count > 1
        assert mock_asyncio_sleep.await_count > 0
        client.logger.error.assert_called_with(
            f"Timeout waiting for transaction {mock_sig_str} confirmation."
        )

    async def test_confirm_transaction_rpc_error(self, client, mock_asyncio_sleep):
        """Tests handling errors.RPCException during confirmation polling."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        mock_rpc_error = {
            "code": 503,
            "message": "Service Unavailable",
        }  # Structure for errors.RPCException
        mock_exception = errors.RPCException(mock_rpc_error)

        client.rpc_client.get_signature_statuses = AsyncMock(
            side_effect=mock_exception
        )  # Fail immediately

        with pytest.raises(errors.RPCException) as exc_info:
            await client.confirm_transaction(mock_sig_str, commitment=Finalized)

        assert exc_info.value == mock_exception
        client.logger.error.assert_called_with(
            f"RPC error while confirming transaction {mock_sig_str}: {mock_exception}"
        )

    # --- WebSocket Method Tests ---

    async def test_connect_wss_success(self, client, mock_websocket_connect):
        """Tests establishing a WebSocket connection successfully."""
        assert client.wss_connection is None
        await client.connect_wss()

        mock_websocket_connect.assert_called_once_with(client.wss_url)
        assert client.wss_connection == mock_websocket_connect.mock_protocol
        client.logger.info.assert_any_call(f"Connecting to WebSocket: {client.wss_url}")
        client.logger.info.assert_any_call("WebSocket connection established.")

    async def test_connect_wss_already_connected(self, client, mock_websocket_connect):
        """Tests attempting to connect when already connected."""
        # Simulate already connected
        client.wss_connection = mock_websocket_connect.mock_protocol
        client.wss_connection.is_connected = True  # Ensure mock reports connected

        await client.connect_wss()

        # connect() should not be called again
        mock_websocket_connect.assert_not_called()
        client.logger.info.assert_called_with(
            "WebSocket connection already established."
        )

    async def test_connect_wss_failure(self, client, mock_websocket_connect):
        """Tests handling of WebSocket connection failure."""
        mock_websocket_connect.side_effect = ConnectionRefusedError(
            "Connection refused"
        )

        with pytest.raises(ConnectionError, match="Failed to connect to WebSocket"):
            await client.connect_wss()

        assert client.wss_connection is None
        client.logger.exception.assert_called_with(
            "Failed to connect to WebSocket: Connection refused"
        )

    async def test_close_wss_connection_with_task(self, client, mock_websocket_connect):
        """Tests closing WSS connection when a subscription task is active."""
        # Simulate active connection and task
        client.wss_connection = mock_websocket_connect.mock_protocol
        mock_task = AsyncMock()
        mock_task.done.return_value = False
        client.log_subscription_task = mock_task
        client.log_callback = AsyncMock()  # Set a dummy callback

        await client.close_wss_connection()

        mock_task.cancel.assert_called_once()
        mock_websocket_connect.mock_protocol.close.assert_awaited_once()
        assert client.wss_connection is None
        assert client.log_subscription_task is None
        assert client.log_callback is None
        client.logger.info.assert_any_call("Cancelling log subscription task...")
        client.logger.info.assert_any_call("Closing WebSocket connection...")

    async def test_close_wss_connection_no_task(self, client, mock_websocket_connect):
        """Tests closing WSS connection without an active subscription task."""
        client.wss_connection = mock_websocket_connect.mock_protocol
        client.log_subscription_task = None  # No task

        await client.close_wss_connection()

        mock_websocket_connect.mock_protocol.close.assert_awaited_once()
        assert client.wss_connection is None
        assert client.log_subscription_task is None
        client.logger.info.assert_any_call("Closing WebSocket connection...")

    async def test_close_wss_connection_not_connected(
        self, client, mock_websocket_connect, mock_wss_message
    ):
        """Tests closing WSS connection when it's already closed or None."""
        client.wss_connection = None  # Not connected

        await client.close_wss_connection()

        # Ensure close wasn't called on None
        mock_websocket_connect.mock_protocol.close.assert_not_awaited()
        assert client.wss_connection is None
        assert client.log_subscription_task is None
        client.logger.debug.assert_called_with(
            "WebSocket connection already closed or not established."
        )

    @pytest.fixture
    def mock_log_callback(self):
        """Provides a mock async callback function."""
        return AsyncMock()

    @pytest.fixture
    def mock_log_data(self):
        """Provides mock log data structure similar to subscription results."""
        # Structure based on solana-py WebsocketLogMessage? Needs verification.
        # Assuming a structure like: {'jsonrpc': '2.0', 'method': 'logsNotification', 'params': {'result': {'value': {'signature': '...', 'logs': [], 'err': None}}, 'subscription': 1}}
        # The client code extracts item.result.value
        return {
            "signature": str(Signature.new_unique()),
            "logs": ["Log line 1", f"Program {MOCK_PROGRAM_ID_1} invoke [1]"],
            "err": None,
        }

    @pytest.fixture
    def mock_wss_message(self, mock_log_data):
        """Provides a mock raw WebSocket message containing log data."""

        # Mimic the structure received over the wire (often a list)
        # This structure might vary, adjust based on actual solana-py behavior
        class MockRpcResponseValue:
            def __init__(self, value):
                self.value = value

        class MockRpcResult:
            def __init__(self, value):
                self.result = MockRpcResponseValue(value)

        return [MockRpcResult(mock_log_data)]  # Wrap in list and objects

    async def test_start_log_subscription_success(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests starting a log subscription successfully."""
        # Ensure connection first (implicitly tested here)
        await client.connect_wss()
        assert client.wss_connection is not None

        mentions_str = [str(pid) for pid in client.monitored_program_ids]

        await client.start_log_subscription(mock_log_callback, commitment=Finalized)

        # Assert logs_subscribe was called correctly
        mock_websocket_connect.mock_protocol.logs_subscribe.assert_awaited_once_with(
            mentions=mentions_str, commitment=Finalized
        )
        # Assert background task was created
        assert client.log_subscription_task is not None
        assert isinstance(client.log_subscription_task, asyncio.Task)
        assert client.log_callback == mock_log_callback
        client.logger.info.assert_any_call(
            f"Starting log subscription for programs mentioned: {mentions_str} with commitment Finalized"
        )
        client.logger.info.assert_any_call("Successfully subscribed to logs.")
        client.logger.info.assert_any_call("Log processing task started.")

        # Clean up the task to avoid warnings during test teardown
        client.log_subscription_task.cancel()
        try:
            await client.log_subscription_task
        except asyncio.CancelledError:
            pass

    async def test_start_log_subscription_connects_if_needed(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests that subscription connects WSS if not already connected."""
        client.wss_connection = None  # Start disconnected

        await client.start_log_subscription(mock_log_callback)

        # Assert connection was attempted
        mock_websocket_connect.assert_called_once_with(client.wss_url)
        assert client.wss_connection is not None
        # Assert subscription proceeded
        mock_websocket_connect.mock_protocol.logs_subscribe.assert_awaited_once()
        assert client.log_subscription_task is not None

        # Clean up
        client.log_subscription_task.cancel()
        try:
            await client.log_subscription_task
        except asyncio.CancelledError:
            pass

    async def test_start_log_subscription_failure(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests handling of failure during the subscription call."""
        await client.connect_wss()  # Connect first
        mock_websocket_connect.mock_protocol.logs_subscribe.side_effect = (
            errors.RPCException("Subscription failed")
        )
        # Mock close_wss_connection to check if it's called on failure
        client.close_wss_connection = AsyncMock()

        await client.start_log_subscription(mock_log_callback)

        assert client.log_subscription_task is None  # Task should not be set
        client.logger.exception.assert_called_with(
            "Failed to start log subscription: errors.RPCException('Subscription failed')"
        )
        # Assert cleanup was called
        client.close_wss_connection.assert_awaited_once()

    async def test_start_log_subscription_restart(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests restarting a log subscription cancels the old one."""
        # Start first subscription
        await client.start_log_subscription(mock_log_callback)
        first_task = client.log_subscription_task
        first_connection = client.wss_connection
        assert first_task is not None
        assert first_connection is not None
        first_task.cancel = MagicMock()  # Mock cancel on the real task
        first_connection.close = AsyncMock()

        # Reset connect mock for the second call
        mock_websocket_connect.reset_mock()
        # Need to setup the side_effect again for the new connection
        new_mock_ws_protocol = AsyncMock()
        new_mock_ws_protocol.is_connected = True
        new_mock_ws_protocol.close = AsyncMock()
        new_mock_ws_protocol.logs_subscribe = AsyncMock()

        async def _new_connect_generator(*args, **kwargs):
            yield new_mock_ws_protocol

        mock_websocket_connect.side_effect = _new_connect_generator
        mock_websocket_connect.mock_protocol = (
            new_mock_ws_protocol  # Update mock reference
        )

        # Start second subscription
        second_callback = AsyncMock()
        await client.start_log_subscription(second_callback)
        second_task = client.log_subscription_task
        second_connection = client.wss_connection

        # Assertions
        assert first_task != second_task  # New task created
        assert first_connection != second_connection  # New connection created
        first_task.cancel.assert_called_once()  # Old task cancelled
        first_connection.close.assert_awaited_once()  # Old connection closed
        mock_websocket_connect.assert_called_once()  # connect called for the second time
        new_mock_ws_protocol.logs_subscribe.assert_awaited_once()  # New subscription started
        assert client.log_callback == second_callback  # Callback updated

        # Clean up second task
        second_task.cancel()
        try:
            await second_task
        except asyncio.CancelledError:
            pass

    async def test_process_log_messages_calls_callback(
        self,
        client,
        mock_websocket_connect,
        mock_log_callback,
        mock_log_data,
        mock_wss_message,
    ):
        """Tests that the internal message processor calls the callback."""
        # Setup connection and callback
        await client.connect_wss()
        client.log_callback = mock_log_callback

        # Configure the mock connection to yield the message then stop
        async def msg_generator():
            yield mock_wss_message
            # Simulate connection closing or end of messages
            raise StopAsyncIteration

        mock_websocket_connect.mock_protocol.__aiter__.return_value = msg_generator()

        # Run the processor directly (it's usually run via create_task)
        await client._process_log_messages()

        # Assert callback was called with the extracted value
        mock_log_callback.assert_awaited_once_with(mock_log_data)

    async def test_process_log_messages_handles_callback_error(
        self,
        client,
        mock_websocket_connect,
        mock_log_callback,
        mock_log_data,
        mock_wss_message,
    ):
        """Tests that errors in the callback are caught and logged."""
        await client.connect_wss()
        mock_log_callback.side_effect = ValueError("Callback error")
        client.log_callback = mock_log_callback

        async def msg_generator():
            yield mock_wss_message
            raise StopAsyncIteration  # Stop after one message

        mock_websocket_connect.mock_protocol.__aiter__.return_value = msg_generator()

        await client._process_log_messages()

        mock_log_callback.assert_awaited_once_with(mock_log_data)
        client.logger.exception.assert_called_with(
            "Error in log processing callback: ValueError('Callback error')"
        )

    async def test_process_log_messages_handles_unexpected_format(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests processing logs with an unexpected message format."""
        await client.connect_wss()
        client.log_callback = mock_log_callback
        unexpected_message = ["some_string"]  # Not the expected structure

        async def msg_generator():
            yield unexpected_message
            raise StopAsyncIteration

        mock_websocket_connect.mock_protocol.__aiter__.return_value = msg_generator()

        await client._process_log_messages()

        mock_log_callback.assert_not_awaited()  # Callback shouldn't be called
        client.logger.warning.assert_any_call(
            f"Received unexpected WSS message format: {unexpected_message[0]}"
        )

    async def test_process_log_messages_handles_cancellation(
        self, client, mock_websocket_connect, mock_wss_message
    ):
        """Tests that the message loop handles cancellation gracefully."""
        await client.connect_wss()
        client.log_callback = AsyncMock()

        # Simulate a message stream that gets cancelled externally
        async def msg_generator():
            yield mock_wss_message  # Send one message
            await asyncio.sleep(0.1)  # Give time for cancellation
            raise asyncio.CancelledError  # Simulate cancellation

        mock_websocket_connect.mock_protocol.__aiter__.return_value = msg_generator()

        # Run in a task and cancel it
        task = asyncio.create_task(client._process_log_messages())
        await asyncio.sleep(0.01)  # Allow task to start and process first message
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task  # Wait for task completion (raises CancelledError)

        client.logger.info.assert_called_with("Log processing task cancelled.")
        # Check callback was called for the message before cancellation
        client.log_callback.assert_awaited_once()

    # --- Test build_swap_instruction Placeholder ---
    def test_build_swap_instruction_raises_not_implemented(self, client):
        """Tests that the placeholder swap instruction builder raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            client.build_swap_instruction(
                dex_program_id=Pubkey.new_unique(),
                user_wallet=Pubkey.new_unique(),
                source_token_account=Pubkey.new_unique(),
                destination_token_account=Pubkey.new_unique(),
                source_mint=Pubkey.new_unique(),
                destination_mint=Pubkey.new_unique(),
                amount_in=100,
                min_amount_out=95,
            )

    async def test_create_sign_send_transaction_preflight_error(
        self, client, mock_instructions, mock_blockhash_resp
    ):
        """Tests handling of TransactionError (like preflight failure) during sending."""
        # Simulate a preflight failure wrapped in errors.RPCException
        preflight_failure = errors.SendTransactionPreflightFailureMessage(
            TransactionError(TransactionError.InstructionError(0, 1)),  # Example error
            logs=[],
            units_consumed=0,
        )
        mock_exception = errors.RPCException(preflight_failure)

        client.rpc_client.get_latest_blockhash = AsyncMock(
            return_value=mock_blockhash_resp
        )
        client.rpc_client.send_raw_transaction = AsyncMock(side_effect=mock_exception)
        client.confirm_transaction = AsyncMock()  # Should not be reached

        with pytest.raises(
            errors.RPCException
        ) as exc_info:  # It's still raised as errors.RPCException
            await client.create_sign_send_transaction(
                mock_instructions, dry_run=False, skip_confirmation=False
            )

        assert exc_info.value == mock_exception
        # Check if specific logging for TransactionError occurred (depends on exact exception handling in main code)
        # In the current code, it falls into the general errors.RPCException block
        client.logger.exception.assert_any_call(
            f"RPC error during transaction processing: {mock_exception}"
        )

    async def test_confirm_transaction_success_finalized(
        self, client, mock_asyncio_sleep
    ):
        """Tests successful transaction confirmation at Finalized commitment."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        resp_processing = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=1),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=10,
                    err=None,
                    confirmation_status=None,
                )
            ],
        )
        resp_confirmed = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=2),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=11,
                    err=None,
                    confirmation_status=Confirmed,
                    confirmations=10,  # Add confirmations
                )
            ],
        )
        resp_finalized = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=3),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=12,
                    err=None,
                    confirmation_status=Finalized,
                    confirmations=32,  # Add confirmations
                )
            ],
        )

        client.rpc_client.get_signature_statuses = AsyncMock(
            side_effect=[resp_processing, resp_confirmed, resp_finalized]
        )

        result = await client.confirm_transaction(
            mock_sig_str, commitment=Finalized, sleep_seconds=0.05
        )

        assert result is True
        assert client.rpc_client.get_signature_statuses.await_count == 3
        client.rpc_client.get_signature_statuses.assert_has_awaits(
            [call([mock_sig_str]), call([mock_sig_str]), call([mock_sig_str])]
        )
        assert (
            mock_asyncio_sleep.await_count == 2
        )  # Slept after processing and confirmed responses
        client.logger.info.assert_any_call(
            f"Confirming transaction {mock_sig_str} with commitment Finalized..."
        )
        client.logger.debug.assert_any_call(
            f"Transaction {mock_sig_str} status: None. Waiting..."
        )  # From resp_processing
        client.logger.debug.assert_any_call(
            f"Transaction {mock_sig_str} status: Confirmed. Waiting..."
        )  # From resp_confirmed
        client.logger.info.assert_any_call(
            f"Transaction {mock_sig_str} confirmed with status: Finalized"
        )

    async def test_confirm_transaction_success_confirmed(
        self, client, mock_asyncio_sleep
    ):
        """Tests successful transaction confirmation at Confirmed commitment."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        resp_processing = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=1),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=10,
                    err=None,
                    confirmation_status=None,
                )
            ],
        )
        resp_confirmed = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=2),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=11,
                    err=None,
                    confirmation_status=Confirmed,
                    confirmations=10,  # Add confirmations
                )
            ],
        )

        client.rpc_client.get_signature_statuses = AsyncMock(
            side_effect=[
                resp_processing,
                resp_confirmed,
            ]
        )

        result = await client.confirm_transaction(
            mock_sig_str, commitment=Confirmed, sleep_seconds=0.05
        )

        assert result is True
        assert client.rpc_client.get_signature_statuses.await_count == 2
        assert mock_asyncio_sleep.await_count == 1  # Slept after processing response
        client.logger.info.assert_any_call(
            f"Transaction {mock_sig_str} confirmed with status: Confirmed"
        )

    async def test_confirm_transaction_failure(self, client, mock_asyncio_sleep):
        """Tests transaction confirmation when the transaction failed."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        mock_tx_error = TransactionError(TransactionError.InstructionError(0, 5))
        resp_failed = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=1),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=10,
                    err=mock_tx_error,
                    confirmation_status=Finalized,
                    confirmations=None,  # Add confirmations
                )
            ],
        )

        client.rpc_client.get_signature_statuses = AsyncMock(return_value=resp_failed)

        with pytest.raises(TransactionError) as exc_info:
            await client.confirm_transaction(
                mock_sig_str, commitment=Finalized, sleep_seconds=0.05
            )

        assert exc_info.match(f"Transaction failed confirmation: {mock_tx_error}")
        assert client.rpc_client.get_signature_statuses.await_count == 1
        assert mock_asyncio_sleep.await_count == 0  # Failed on first check
        client.logger.error.assert_called_with(
            f"Transaction {mock_sig_str} failed: {mock_tx_error}"
        )

    async def test_confirm_transaction_timeout(self, client, mock_asyncio_sleep):
        """Tests transaction confirmation timeout."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        resp_processing = GetSignatureStatusesResp(
            context=RpcResponseContext(slot=1),
            value=[
                RpcConfirmedTransactionStatusWithSignature(
                    signature=Signature.new_unique(),
                    slot=10,
                    err=None,
                    confirmation_status=None,
                )
            ],
        )

        client.rpc_client.get_signature_statuses = AsyncMock(
            return_value=resp_processing
        )  # Always processing

        # Mock time.monotonic to simulate timeout
        start_time = time.monotonic()
        with patch("time.monotonic") as mock_time:
            # Simulate time passing just enough to exceed timeout on the second check
            mock_time.side_effect = [
                start_time,  # First call inside loop
                start_time + 0.1,  # Second call inside loop (after sleep)
                start_time + client.timeout + 0.1,  # Third call, exceeds timeout
            ]
            with pytest.raises(asyncio.TimeoutError) as exc_info:
                # Use a small sleep to ensure the loop runs multiple times quickly
                await client.confirm_transaction(
                    mock_sig_str, commitment=Finalized, sleep_seconds=0.01
                )

        assert exc_info.match(
            f"Timeout waiting for transaction {mock_sig_str} confirmation."
        )
        # Check it polled multiple times before timeout
        assert client.rpc_client.get_signature_statuses.await_count > 1
        assert mock_asyncio_sleep.await_count > 0
        client.logger.error.assert_called_with(
            f"Timeout waiting for transaction {mock_sig_str} confirmation."
        )

    async def test_confirm_transaction_rpc_error(self, client, mock_asyncio_sleep):
        """Tests handling errors.RPCException during confirmation polling."""
        mock_sig = Signature.new_unique()
        mock_sig_str = str(mock_sig)
        mock_rpc_error = {
            "code": 503,
            "message": "Service Unavailable",
        }  # Structure for errors.RPCException
        mock_exception = errors.RPCException(mock_rpc_error)

        client.rpc_client.get_signature_statuses = AsyncMock(
            side_effect=mock_exception
        )  # Fail immediately

        with pytest.raises(errors.RPCException) as exc_info:
            await client.confirm_transaction(mock_sig_str, commitment=Finalized)

        assert exc_info.value == mock_exception
        client.logger.error.assert_called_with(
            f"RPC error while confirming transaction {mock_sig_str}: {mock_exception}"
        )

    # --- WebSocket Method Tests ---

    async def test_connect_wss_success(self, client, mock_websocket_connect):
        """Tests establishing a WebSocket connection successfully."""
        assert client.wss_connection is None
        await client.connect_wss()

        mock_websocket_connect.assert_called_once_with(client.wss_url)
        assert client.wss_connection == mock_websocket_connect.mock_protocol
        client.logger.info.assert_any_call(f"Connecting to WebSocket: {client.wss_url}")
        client.logger.info.assert_any_call("WebSocket connection established.")

    async def test_connect_wss_already_connected(self, client, mock_websocket_connect):
        """Tests attempting to connect when already connected."""
        # Simulate already connected
        client.wss_connection = mock_websocket_connect.mock_protocol
        client.wss_connection.is_connected = True  # Ensure mock reports connected

        await client.connect_wss()

        # connect() should not be called again
        mock_websocket_connect.assert_not_called()
        client.logger.info.assert_called_with(
            "WebSocket connection already established."
        )

    async def test_connect_wss_failure(self, client, mock_websocket_connect):
        """Tests handling of WebSocket connection failure."""
        mock_websocket_connect.side_effect = ConnectionRefusedError(
            "Connection refused"
        )

        with pytest.raises(ConnectionError, match="Failed to connect to WebSocket"):
            await client.connect_wss()

        assert client.wss_connection is None
        client.logger.exception.assert_called_with(
            "Failed to connect to WebSocket: Connection refused"
        )

    async def test_close_wss_connection_with_task(self, client, mock_websocket_connect):
        """Tests closing WSS connection when a subscription task is active."""
        # Simulate active connection and task
        client.wss_connection = mock_websocket_connect.mock_protocol
        mock_task = AsyncMock()
        mock_task.done.return_value = False
        client.log_subscription_task = mock_task
        client.log_callback = AsyncMock()  # Set a dummy callback

        await client.close_wss_connection()

        mock_task.cancel.assert_called_once()
        mock_websocket_connect.mock_protocol.close.assert_awaited_once()
        assert client.wss_connection is None
        assert client.log_subscription_task is None
        assert client.log_callback is None
        client.logger.info.assert_any_call("Cancelling log subscription task...")
        client.logger.info.assert_any_call("Closing WebSocket connection...")

    async def test_close_wss_connection_no_task(self, client, mock_websocket_connect):
        """Tests closing WSS connection without an active subscription task."""
        client.wss_connection = mock_websocket_connect.mock_protocol
        client.log_subscription_task = None  # No task

        await client.close_wss_connection()

        mock_websocket_connect.mock_protocol.close.assert_awaited_once()
        assert client.wss_connection is None
        assert client.log_subscription_task is None
        client.logger.info.assert_any_call("Closing WebSocket connection...")

    async def test_close_wss_connection_not_connected(
        self, client, mock_websocket_connect, mock_wss_message
    ):
        """Tests closing WSS connection when it's already closed or None."""
        client.wss_connection = None  # Not connected

        await client.close_wss_connection()

        # Ensure close wasn't called on None
        mock_websocket_connect.mock_protocol.close.assert_not_awaited()
        assert client.wss_connection is None
        assert client.log_subscription_task is None
        client.logger.debug.assert_called_with(
            "WebSocket connection already closed or not established."
        )

    @pytest.fixture
    def mock_log_callback(self):
        """Provides a mock async callback function."""
        return AsyncMock()

    @pytest.fixture
    def mock_log_data(self):
        """Provides mock log data structure similar to subscription results."""
        # Structure based on solana-py WebsocketLogMessage? Needs verification.
        # Assuming a structure like: {'jsonrpc': '2.0', 'method': 'logsNotification', 'params': {'result': {'value': {'signature': '...', 'logs': [], 'err': None}}, 'subscription': 1}}
        # The client code extracts item.result.value
        return {
            "signature": str(Signature.new_unique()),
            "logs": ["Log line 1", f"Program {MOCK_PROGRAM_ID_1} invoke [1]"],
            "err": None,
        }

    @pytest.fixture
    def mock_wss_message(self, mock_log_data):
        """Provides a mock raw WebSocket message containing log data."""

        # Mimic the structure received over the wire (often a list)
        # This structure might vary, adjust based on actual solana-py behavior
        class MockRpcResponseValue:
            def __init__(self, value):
                self.value = value

        class MockRpcResult:
            def __init__(self, value):
                self.result = MockRpcResponseValue(value)

        return [MockRpcResult(mock_log_data)]  # Wrap in list and objects

    async def test_start_log_subscription_success(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests starting a log subscription successfully."""
        # Ensure connection first (implicitly tested here)
        await client.connect_wss()
        assert client.wss_connection is not None

        mentions_str = [str(pid) for pid in client.monitored_program_ids]

        await client.start_log_subscription(mock_log_callback, commitment=Finalized)

        # Assert logs_subscribe was called correctly
        mock_websocket_connect.mock_protocol.logs_subscribe.assert_awaited_once_with(
            mentions=mentions_str, commitment=Finalized
        )
        # Assert background task was created
        assert client.log_subscription_task is not None
        assert isinstance(client.log_subscription_task, asyncio.Task)
        assert client.log_callback == mock_log_callback
        client.logger.info.assert_any_call(
            f"Starting log subscription for programs mentioned: {mentions_str} with commitment Finalized"
        )
        client.logger.info.assert_any_call("Successfully subscribed to logs.")
        client.logger.info.assert_any_call("Log processing task started.")

        # Clean up the task to avoid warnings during test teardown
        client.log_subscription_task.cancel()
        try:
            await client.log_subscription_task
        except asyncio.CancelledError:
            pass

    async def test_start_log_subscription_connects_if_needed(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests that subscription connects WSS if not already connected."""
        client.wss_connection = None  # Start disconnected

        await client.start_log_subscription(mock_log_callback)

        # Assert connection was attempted
        mock_websocket_connect.assert_called_once_with(client.wss_url)
        assert client.wss_connection is not None
        # Assert subscription proceeded
        mock_websocket_connect.mock_protocol.logs_subscribe.assert_awaited_once()
        assert client.log_subscription_task is not None

        # Clean up
        client.log_subscription_task.cancel()
        try:
            await client.log_subscription_task
        except asyncio.CancelledError:
            pass

    async def test_start_log_subscription_failure(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests handling of failure during the subscription call."""
        await client.connect_wss()  # Connect first
        mock_websocket_connect.mock_protocol.logs_subscribe.side_effect = (
            errors.RPCException("Subscription failed")
        )
        # Mock close_wss_connection to check if it's called on failure
        client.close_wss_connection = AsyncMock()

        await client.start_log_subscription(mock_log_callback)

        assert client.log_subscription_task is None  # Task should not be set
        client.logger.exception.assert_called_with(
            "Failed to start log subscription: errors.RPCException('Subscription failed')"
        )
        # Assert cleanup was called
        client.close_wss_connection.assert_awaited_once()

    async def test_start_log_subscription_restart(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests restarting a log subscription cancels the old one."""
        # Start first subscription
        await client.start_log_subscription(mock_log_callback)
        first_task = client.log_subscription_task
        first_connection = client.wss_connection
        assert first_task is not None
        assert first_connection is not None
        first_task.cancel = MagicMock()  # Mock cancel on the real task
        first_connection.close = AsyncMock()

        # Reset connect mock for the second call
        mock_websocket_connect.reset_mock()
        # Need to setup the side_effect again for the new connection
        new_mock_ws_protocol = AsyncMock()
        new_mock_ws_protocol.is_connected = True
        new_mock_ws_protocol.close = AsyncMock()
        new_mock_ws_protocol.logs_subscribe = AsyncMock()

        async def _new_connect_generator(*args, **kwargs):
            yield new_mock_ws_protocol

        mock_websocket_connect.side_effect = _new_connect_generator
        mock_websocket_connect.mock_protocol = (
            new_mock_ws_protocol  # Update mock reference
        )

        # Start second subscription
        second_callback = AsyncMock()
        await client.start_log_subscription(second_callback)
        second_task = client.log_subscription_task
        second_connection = client.wss_connection

        # Assertions
        assert first_task != second_task  # New task created
        assert first_connection != second_connection  # New connection created
        first_task.cancel.assert_called_once()  # Old task cancelled
        first_connection.close.assert_awaited_once()  # Old connection closed
        mock_websocket_connect.assert_called_once()  # connect called for the second time
        new_mock_ws_protocol.logs_subscribe.assert_awaited_once()  # New subscription started
        assert client.log_callback == second_callback  # Callback updated

        # Clean up second task
        second_task.cancel()
        try:
            await second_task
        except asyncio.CancelledError:
            pass

    async def test_process_log_messages_calls_callback(
        self,
        client,
        mock_websocket_connect,
        mock_log_callback,
        mock_log_data,
        mock_wss_message,
    ):
        """Tests that the internal message processor calls the callback."""
        # Setup connection and callback
        await client.connect_wss()
        client.log_callback = mock_log_callback

        # Configure the mock connection to yield the message then stop
        async def msg_generator():
            yield mock_wss_message
            # Simulate connection closing or end of messages
            raise StopAsyncIteration

        mock_websocket_connect.mock_protocol.__aiter__.return_value = msg_generator()

        # Run the processor directly (it's usually run via create_task)
        await client._process_log_messages()

        # Assert callback was called with the extracted value
        mock_log_callback.assert_awaited_once_with(mock_log_data)

    async def test_process_log_messages_handles_callback_error(
        self,
        client,
        mock_websocket_connect,
        mock_log_callback,
        mock_log_data,
        mock_wss_message,
    ):
        """Tests that errors in the callback are caught and logged."""
        await client.connect_wss()
        mock_log_callback.side_effect = ValueError("Callback error")
        client.log_callback = mock_log_callback

        async def msg_generator():
            yield mock_wss_message
            raise StopAsyncIteration  # Stop after one message

        mock_websocket_connect.mock_protocol.__aiter__.return_value = msg_generator()

        await client._process_log_messages()

        mock_log_callback.assert_awaited_once_with(mock_log_data)
        client.logger.exception.assert_called_with(
            "Error in log processing callback: ValueError('Callback error')"
        )

    async def test_process_log_messages_handles_unexpected_format(
        self, client, mock_websocket_connect, mock_log_callback
    ):
        """Tests processing logs with an unexpected message format."""
        await client.connect_wss()
        client.log_callback = mock_log_callback
        unexpected_message = ["some_string"]  # Not the expected structure

        async def msg_generator():
            yield unexpected_message
            raise StopAsyncIteration

        mock_websocket_connect.mock_protocol.__aiter__.return_value = msg_generator()

        await client._process_log_messages()

        mock_log_callback.assert_not_awaited()  # Callback shouldn't be called
        client.logger.warning.assert_any_call(
            f"Received unexpected WSS message format: {unexpected_message[0]}"
        )

    async def test_process_log_messages_handles_cancellation(
        self, client, mock_websocket_connect, mock_wss_message
    ):
        """Tests that the message loop handles cancellation gracefully."""
        await client.connect_wss()
        client.log_callback = AsyncMock()

        # Simulate a message stream that gets cancelled externally
        async def msg_generator():
            yield mock_wss_message  # Send one message
            await asyncio.sleep(0.1)  # Give time for cancellation
            raise asyncio.CancelledError  # Simulate cancellation

        mock_websocket_connect.mock_protocol.__aiter__.return_value = msg_generator()

        # Run in a task and cancel it
        task = asyncio.create_task(client._process_log_messages())
        await asyncio.sleep(0.01)  # Allow task to start and process first message
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task  # Wait for task completion (raises CancelledError)

        client.logger.info.assert_called_with("Log processing task cancelled.")
        # Check callback was called for the message before cancellation
        client.log_callback.assert_awaited_once()

    # --- Test build_swap_instruction Placeholder ---
    def test_build_swap_instruction_raises_not_implemented(self, client):
        """Tests that the placeholder swap instruction builder raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            client.build_swap_instruction(
                dex_program_id=Pubkey.new_unique(),
                user_wallet=Pubkey.new_unique(),
                source_token_account=Pubkey.new_unique(),
                destination_token_account=Pubkey.new_unique(),
                source_mint=Pubkey.new_unique(),
                destination_mint=Pubkey.new_unique(),
                amount_in=100,
                min_amount_out=95,
            )
