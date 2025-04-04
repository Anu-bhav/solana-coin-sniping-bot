# tests/database/test_manager.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys
import asyncpg  # Import asyncpg for spec

# Ensure src directory is in path for imports
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager  # noqa: E402

# --- Fixtures ---

DUMMY_DSN = "postgresql://mock_user:mock_pass@mock_host:5432/mock_db"


@pytest.fixture
def mock_asyncpg_pool():
    """Mocks the asyncpg connection pool."""
    mock_pool = AsyncMock(spec=asyncpg.Pool)
    mock_conn = AsyncMock(spec=asyncpg.Connection)
    # Corrected spec to lowercase 'transaction'
    # Removed unused mock_transaction variable
    # mock_transaction = AsyncMock(spec=asyncpg.transaction)

    # Configure mock connection methods
    mock_conn.execute = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.fetchval = AsyncMock(return_value=None)
    # Mock commit/rollback methods directly on the connection mock
    mock_conn.commit = AsyncMock()
    mock_conn.rollback = AsyncMock()

    # --- Corrected Transaction Mocking ---
    # Create a separate mock for the transaction context manager
    mock_tx_ctx_manager = AsyncMock()

    async def transaction_aenter(*args, **kwargs):
        # print("DEBUG: Mock Transaction Context Manager __aenter__ called")
        # __aenter__ usually returns self, but the code doesn't use 'as ...:'
        return mock_tx_ctx_manager

    async def transaction_aexit(exc_type, exc, tb):
        # print(f"DEBUG: Mock Transaction Context Manager __aexit__ called with {exc_type}")
        # The context manager calls commit/rollback on the connection
        if exc_type:
            # print("DEBUG: Rolling back via connection mock")
            await mock_conn.rollback()  # Call rollback on the connection mock
        else:
            # print("DEBUG: Committing via connection mock")
            await mock_conn.commit()  # Call commit on the connection mock

    mock_tx_ctx_manager.__aenter__ = AsyncMock(side_effect=transaction_aenter)
    mock_tx_ctx_manager.__aexit__ = AsyncMock(side_effect=transaction_aexit)

    # Make conn.transaction() return the context manager mock
    mock_conn.transaction = MagicMock(return_value=mock_tx_ctx_manager)
    # --- End Corrected Transaction Mocking ---

    # Configure pool acquire context manager
    async def acquire_aenter(*args, **kwargs):
        # print("DEBUG: Mock Pool Acquire __aenter__ called")
        return mock_conn

    async def acquire_aexit(exc_type, exc, tb):
        # print(f"DEBUG: Mock Pool Acquire __aexit__ called with {exc_type}")
        pass  # Simulate releasing connection

    mock_pool.acquire = MagicMock()  # Make acquire itself a MagicMock
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(side_effect=acquire_aenter)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(side_effect=acquire_aexit)

    # Configure other pool methods if needed
    mock_pool.close = AsyncMock()

    # Return the context manager mock instead of the old transaction mock
    return mock_pool, mock_conn, mock_tx_ctx_manager


@pytest.fixture
def db_manager():
    """Provides an instance of DatabaseManager initialized with a dummy DSN."""
    # No config object needed now, just the DSN
    manager = DatabaseManager(dsn=DUMMY_DSN)
    manager.pool = None  # Ensure pool is reset for tests
    return manager


# --- Helper Function for Resets ---


# Updated signature to accept the context manager mock
def reset_asyncpg_mocks(mock_pool, mock_conn, mock_tx_ctx_manager):
    """Resets relevant asyncpg mocks."""
    mock_pool.reset_mock()
    mock_pool.acquire.reset_mock()
    mock_pool.close.reset_mock()

    mock_conn.reset_mock()
    mock_conn.execute.reset_mock()
    mock_conn.fetch.reset_mock()
    mock_conn.fetchrow.reset_mock()
    mock_conn.fetchval.reset_mock()
    mock_conn.transaction.reset_mock()
    # Also reset the context manager mock itself
    mock_tx_ctx_manager.reset_mock()
    # Removed lines referencing the old mock_transaction


# --- Test Cases ---


@pytest.mark.asyncio
async def test_db_manager_initialization(db_manager):
    """Test that DatabaseManager initializes correctly."""
    assert db_manager.dsn == DUMMY_DSN
    assert db_manager.pool is None


@pytest.mark.asyncio
@patch("asyncpg.create_pool", new_callable=AsyncMock)
async def test_connect(mock_create_pool, db_manager, mock_asyncpg_pool):
    """Test establishing the connection pool."""
    mock_pool, _, _ = mock_asyncpg_pool
    mock_create_pool.return_value = mock_pool

    reset_asyncpg_mocks(mock_pool, _, _)  # Reset mocks before call
    mock_create_pool.reset_mock()

    await db_manager.connect()

    mock_create_pool.assert_called_once_with(
        dsn=DUMMY_DSN, min_size=2, max_size=10, command_timeout=60
    )
    assert db_manager.pool == mock_pool


@pytest.mark.asyncio
@patch("asyncpg.create_pool", new_callable=AsyncMock)
async def test_close(mock_create_pool, db_manager, mock_asyncpg_pool):
    """Test closing the connection pool."""
    mock_pool, mock_conn, mock_transaction = mock_asyncpg_pool
    mock_create_pool.return_value = mock_pool

    # Establish connection first
    await db_manager.connect()
    assert db_manager.pool is mock_pool

    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)

    # Close connection
    await db_manager.close()
    mock_pool.close.assert_called_once()
    # assert db_manager.pool is None # Pool object might still be assigned

    # Closing again should do nothing if pool is already closed or None
    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)
    db_manager.pool = None  # Simulate pool being gone
    await db_manager.close()
    mock_pool.close.assert_not_called()


# --- CRUD Tests ---


@pytest.mark.asyncio
@patch("asyncpg.create_pool", new_callable=AsyncMock)
async def test_add_detection(mock_create_pool, db_manager, mock_asyncpg_pool):
    """Test adding a detection record."""
    mock_pool, mock_conn, mock_transaction = mock_asyncpg_pool
    # Simulate connection pool already being set up
    db_manager.pool = mock_pool

    token = "TokenMint1"
    lp = "LPAddr1"
    base = "BaseMint1"
    creator = "Creator1"

    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)

    await db_manager.add_detection(token, lp, base, creator)

    # Check acquire was used
    mock_pool.acquire.assert_called_once()
    # Check transaction was started
    mock_conn.transaction.assert_called_once()
    # Check execute was called within transaction
    expected_sql = """
                    INSERT INTO detections (token_mint, lp_address, base_mint, creator_address)
                    VALUES ($1, $2, $3, $4)
                """
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    assert args[1:] == (token, lp, base, creator)  # Check parameters passed to execute
    # Check transaction commit/rollback (should commit on success via connection mock)
    mock_conn.commit.assert_called_once()
    mock_conn.rollback.assert_not_called()


@pytest.mark.asyncio
@patch("asyncpg.create_pool", new_callable=AsyncMock)
async def test_update_detection_status(mock_create_pool, db_manager, mock_asyncpg_pool):
    """Test updating detection status."""
    mock_pool, mock_conn, mock_transaction = mock_asyncpg_pool
    db_manager.pool = mock_pool

    token = "TokenMint1"
    status = "PASSED_FILTER"
    reason = "Looks good"

    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)

    await db_manager.update_detection_status(token, status, reason)

    mock_pool.acquire.assert_called_once()
    mock_conn.transaction.assert_called_once()
    expected_sql = """
                    UPDATE detections
                    SET status = $1, filter_fail_reason = $2
                    WHERE token_mint = $3
                """
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    assert args[1:] == (status, reason, token)
    mock_conn.commit.assert_called_once()
    mock_conn.rollback.assert_not_called()


@pytest.mark.asyncio
@patch("asyncpg.create_pool", new_callable=AsyncMock)
async def test_add_position(mock_create_pool, db_manager, mock_asyncpg_pool):
    """Test adding a position record."""
    mock_pool, mock_conn, mock_transaction = mock_asyncpg_pool
    db_manager.pool = mock_pool

    token = "TokenMintPos1"
    lp = "LPAddrPos1"
    buy_sol = 0.1
    buy_sig = "BuySig1"
    buy_tokens = 1000.0
    buy_price = 0.0001
    buy_provider = "ProviderX"

    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)

    await db_manager.add_position(
        token, lp, buy_sol, buy_tokens, buy_price, buy_sig, buy_provider
    )

    mock_pool.acquire.assert_called_once()
    mock_conn.transaction.assert_called_once()
    expected_sql = """
                    INSERT INTO positions (token_mint, lp_address, buy_amount_sol,
                                        buy_amount_tokens, buy_price, buy_tx_signature,
                                        buy_provider_identifier)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT(token_mint) DO UPDATE SET
                        lp_address = excluded.lp_address,
                        buy_amount_sol = excluded.buy_amount_sol,
                        buy_amount_tokens = excluded.buy_amount_tokens,
                        buy_price = excluded.buy_price,
                        buy_tx_signature = excluded.buy_tx_signature,
                        buy_provider_identifier = excluded.buy_provider_identifier,
                        last_updated = CURRENT_TIMESTAMP
                """
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    assert args[1:] == (
        token,
        lp,
        buy_sol,
        buy_tokens,
        buy_price,
        buy_sig,
        buy_provider,
    )
    mock_conn.commit.assert_called_once()
    mock_conn.rollback.assert_not_called()


@pytest.mark.asyncio
@patch("asyncpg.create_pool", new_callable=AsyncMock)
async def test_get_active_position(mock_create_pool, db_manager, mock_asyncpg_pool):
    """Test retrieving a specific active position."""
    mock_pool, mock_conn, mock_transaction = mock_asyncpg_pool
    db_manager.pool = mock_pool

    token = "TokenMintActive"
    # Simulate asyncpg returning a Record object (mock it like a dict)
    mock_record_data = {"id": 1, "token_mint": token, "status": "ACTIVE"}
    mock_record = MagicMock(spec=asyncpg.Record)
    # Make the mock record behave like a dictionary for the test assertion
    mock_record.__getitem__.side_effect = lambda key: mock_record_data[key]
    # mock_conn.fetchrow.return_value = mock_record  # Set after reset

    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)
    # Set return value *after* reset and *before* the call
    # Return the dictionary directly, mimicking the manager's dict(row) conversion
    mock_conn.fetchrow.return_value = mock_record_data

    position = await db_manager.get_active_position(token)

    assert position is not None
    assert position["token_mint"] == token
    assert position["status"] == "ACTIVE"
    expected_sql = """
                SELECT * FROM positions
                WHERE token_mint = $1 AND status = 'ACTIVE'
            """
    mock_pool.acquire.assert_called_once()
    mock_conn.fetchrow.assert_called_once()
    args, _ = mock_conn.fetchrow.call_args
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    assert args[1:] == (token,)
    # No transaction expected for fetch
    mock_conn.transaction.assert_not_called()


@pytest.mark.asyncio
@patch("asyncpg.create_pool", new_callable=AsyncMock)
async def test_get_all_active_positions(
    mock_create_pool, db_manager, mock_asyncpg_pool
):
    """Test retrieving all active positions."""
    mock_pool, mock_conn, mock_transaction = mock_asyncpg_pool
    db_manager.pool = mock_pool

    # Simulate returning multiple records as dictionaries (as the manager converts them)
    record1_data = {"id": 1, "token_mint": "Token1", "status": "ACTIVE"}
    record2_data = {"id": 2, "token_mint": "Token2", "status": "ACTIVE"}
    # record1 = MagicMock(spec=asyncpg.Record)
    # record1.__getitem__.side_effect = lambda k: record1_data[k]
    # record2 = MagicMock(spec=asyncpg.Record)
    # record2.__getitem__.side_effect = lambda k: record2_data[k]
    mock_records_as_dicts = [record1_data, record2_data]
    # mock_conn.fetch.return_value = mock_records # Set after reset

    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)
    # Set fetch to return dicts directly, mimicking the manager's conversion
    mock_conn.fetch.return_value = mock_records_as_dicts

    positions = await db_manager.get_all_active_positions()

    assert len(positions) == 2
    assert positions[0]["token_mint"] == "Token1"
    assert positions[1]["token_mint"] == "Token2"
    expected_sql = """
                SELECT * FROM positions
                WHERE status = 'ACTIVE'
                ORDER BY buy_timestamp DESC
            """
    mock_pool.acquire.assert_called_once()
    mock_conn.fetch.assert_called_once()
    args, _ = mock_conn.fetch.call_args
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    # No transaction expected for fetch
    mock_conn.transaction.assert_not_called()


@pytest.mark.asyncio
@patch("asyncpg.create_pool", new_callable=AsyncMock)
async def test_check_if_token_processed(
    mock_create_pool, db_manager, mock_asyncpg_pool
):
    """Test checking if a token exists in detections or positions."""
    mock_pool, mock_conn, mock_transaction = mock_asyncpg_pool
    db_manager.pool = mock_pool

    # Test case 1: Token exists (fetchval returns True)
    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)
    mock_conn.fetchval.return_value = True
    processed = await db_manager.check_if_token_processed("ExistingToken")
    assert processed is True
    mock_pool.acquire.assert_called_once()
    mock_conn.fetchval.assert_called_once()
    args, _ = mock_conn.fetchval.call_args
    assert args[1:] == ("ExistingToken",)  # Check token passed as arg
    # Verify SQL uses EXISTS and checks relevant statuses
    assert "SELECT EXISTS(" in args[0]
    assert "detections" in args[0]
    assert "positions" in args[0]
    assert "UNION ALL" in args[0]
    assert (
        "status IN ('PASSED_FILTER', 'FAILED_FILTER', 'BUY_PENDING', 'BUY_FAILED')"
        in args[0]
    )
    assert "status IN ('ACTIVE', 'SELL_PENDING', 'SELL_FAILED')" in args[0]

    # Test case 2: Token does not exist (fetchval returns False)
    reset_asyncpg_mocks(mock_pool, mock_conn, mock_transaction)
    mock_conn.fetchval.return_value = False
    processed = await db_manager.check_if_token_processed("NewToken")
    assert processed is False
    mock_pool.acquire.assert_called_once()
    mock_conn.fetchval.assert_called_once()
    args, _ = mock_conn.fetchval.call_args
    assert args[1:] == ("NewToken",)


# Note: The original tests for aiosqlite had more specific checks for
# commit counts, cursor calls, row factory etc. These are less relevant
# or structured differently with asyncpg's pool/connection/transaction model.
# The focus here is on ensuring the correct asyncpg methods (execute, fetchrow, etc.)
# are called with the right SQL and parameters within the expected transaction context.

# Add tests for other DatabaseManager methods if they exist and need testing.
# e.g., update_position_status, move_position_to_trades
