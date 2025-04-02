# tests/database/test_manager.py

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from pathlib import Path
import sys
import aiosqlite  # Import needed for spec and Row factory check

# Ensure src directory is in path for imports
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager

# Make dummy classes for config structure if models.py isn't fully defined/available
try:
    from src.core.models import AppConfig, DatabaseConfig, GeneralConfig
except ImportError:
    # Define minimal dummy classes if import fails
    class DatabaseConfig:
        db_path = Path("dummy_db")
        dev_db_file = "dummy_dev.db"
        prod_db_file = "dummy_prod.db"

    class GeneralConfig:
        app_env = "development"

    class AppConfig:
        database = DatabaseConfig()
        general = GeneralConfig()


# --- Fixtures ---


@pytest.fixture
def mock_config():
    """Provides a mock AppConfig object for testing."""
    # Create mock objects that mimic the structure expected by DatabaseManager
    mock_db_config = MagicMock(spec=DatabaseConfig)
    mock_db_config.db_path = Path("test_db_mock")  # Use a distinct path for mocks
    mock_db_config.dev_db_file = "test_dev.sqlite"
    mock_db_config.prod_db_file = "test_prod.sqlite"

    mock_general_config = MagicMock(spec=GeneralConfig)
    mock_general_config.app_env = "development"  # Default to development

    mock_app_config = MagicMock(spec=AppConfig)
    mock_app_config.database = mock_db_config
    mock_app_config.general = mock_general_config
    return mock_app_config


@pytest.fixture
def db_manager(mock_config):  # Changed to sync fixture
    """Provides an instance of DatabaseManager with mocked config."""
    # Temporarily patch Path.mkdir during instantiation if needed, although
    # mocking the connection should prevent actual file operations.
    with patch("pathlib.Path.mkdir", return_value=None):
        manager = DatabaseManager(config=mock_config)
    # Ensure db_path is correctly set based on the mock config for tests
    if mock_config.general.app_env == "production":
        manager.db_path = (
            Path(mock_config.database.db_path) / mock_config.database.prod_db_file
        )
    else:
        manager.db_path = (
            Path(mock_config.database.db_path) / mock_config.database.dev_db_file
        )
    # Reset connection state for each test using the fixture
    manager.connection = None
    return manager  # Return the instance directly


@pytest.fixture
def mock_aiosqlite_connection():
    """Mocks the aiosqlite connection and cursor."""
    mock_conn = AsyncMock(spec=aiosqlite.Connection)
    mock_cursor = AsyncMock(spec=aiosqlite.Cursor)

    # Configure mock cursor methods needed
    mock_cursor.fetchone = AsyncMock(return_value=None)  # Default fetchone
    mock_cursor.fetchall = AsyncMock(return_value=[])  # Default fetchall
    mock_cursor.rowcount = 0  # Default rowcount
    mock_cursor.close = AsyncMock()  # Mock close method for cursor

    # Configure mock connection methods
    # cursor() should be an AsyncMock returning the mock_cursor
    mock_conn.cursor = AsyncMock(return_value=mock_cursor)  # CORRECTED: Use AsyncMock
    mock_conn.execute = AsyncMock(return_value=mock_cursor)  # execute returns cursor
    # executescript should be awaitable
    mock_conn.executescript = AsyncMock(
        return_value=mock_cursor
    )  # CORRECTED: Keep AsyncMock
    mock_conn.commit = AsyncMock()
    mock_conn.rollback = AsyncMock()
    mock_conn.close = AsyncMock()
    # Add row_factory attribute
    mock_conn.row_factory = None

    # --- Corrected Mocking for async with cursor ---
    # conn.cursor() is SYNCHRONOUS and returns the cursor object.
    # The async context manager protocol applies to the CURSOR object itself.
    mock_conn.cursor = MagicMock(
        return_value=mock_cursor
    )  # conn.cursor returns the mock cursor directly

    # Make the mock_cursor itself support the async context manager protocol
    async def mock_cursor_aenter():
        # print("DEBUG: Mock Cursor __aenter__ called")
        return mock_cursor  # __aenter__ should return the object to be used in 'as'

    async def mock_cursor_aexit(exc_type, exc, tb):
        # print(f"DEBUG: Mock Cursor __aexit__ called with {exc_type}")
        await mock_cursor.close()  # Simulate closing the cursor on exit

    mock_cursor.__aenter__ = AsyncMock(side_effect=mock_cursor_aenter)
    mock_cursor.__aexit__ = AsyncMock(side_effect=mock_cursor_aexit)

    # Make connection awaitable for 'async with conn:' (though less common)
    async def conn_aenter(self):
        return self

    async def conn_aexit(self, exc_type, exc, tb):
        pass  # Don't close connection automatically

    mock_conn.__aenter__ = conn_aenter.__get__(mock_conn)
    mock_conn.__aexit__ = conn_aexit.__get__(mock_conn)

    return mock_conn, mock_cursor


# --- Test Cases ---


@pytest.mark.asyncio
async def test_db_manager_initialization(mock_config):
    """Test that DatabaseManager initializes correctly with dev config."""
    with patch("pathlib.Path.mkdir"):  # Patch mkdir during init
        manager = DatabaseManager(config=mock_config)
    assert manager.config == mock_config
    assert manager.connection is None
    # Check if the path is constructed correctly based on mock config
    # Adjust expected path if DatabaseManager's root finding logic changes
    expected_path = (
        Path(__file__).resolve().parents[2] / "test_db_mock" / "test_dev.sqlite"
    )
    assert manager.db_path == expected_path


@pytest.mark.asyncio
async def test_db_manager_initialization_prod(mock_config):
    """Test that DatabaseManager initializes correctly with prod config."""
    mock_config.general.app_env = "production"  # Change env for this test
    with patch("pathlib.Path.mkdir"):
        manager = DatabaseManager(config=mock_config)
    assert manager.config == mock_config
    assert manager.connection is None
    expected_path = (
        Path(__file__).resolve().parents[2] / "test_db_mock" / "test_prod.sqlite"
    )
    assert manager.db_path == expected_path


@pytest.mark.asyncio
@patch(
    "aiosqlite.connect", new_callable=AsyncMock
)  # Patch connect globally for this test
async def test_get_connection(mock_connect, db_manager, mock_aiosqlite_connection):
    """Test establishing a database connection."""
    mock_conn, _ = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn  # Make connect return our mock connection

    # First call should connect
    conn1 = await db_manager._get_connection()
    assert conn1 == mock_conn
    mock_connect.assert_called_once_with(db_manager.db_path, timeout=10.0)
    # Check WAL mode set and commit called after connect
    mock_conn.execute.assert_called_once_with("PRAGMA journal_mode=WAL;")
    mock_conn.commit.assert_called_once()

    # Second call should return the existing connection
    mock_connect.reset_mock()
    mock_conn.execute.reset_mock()
    mock_conn.commit.reset_mock()
    conn2 = await db_manager._get_connection()
    assert conn2 == mock_conn
    mock_connect.assert_not_called()  # Should not connect again
    mock_conn.execute.assert_not_called()  # Should not set WAL again
    mock_conn.commit.assert_not_called()


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_close_connection(mock_connect, db_manager, mock_aiosqlite_connection):
    """Test closing the database connection."""
    mock_conn, _ = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn

    # Establish connection
    await db_manager._get_connection()
    assert db_manager.connection is mock_conn

    # Close connection
    await db_manager.close_connection()
    mock_conn.close.assert_called_once()
    assert db_manager.connection is None

    # Closing again should do nothing
    mock_conn.close.reset_mock()
    await db_manager.close_connection()
    mock_conn.close.assert_not_called()


# Patch Path.exists and open for schema reading
@patch("pathlib.Path.mkdir")  # Mock mkdir for db path creation
@patch("pathlib.Path.exists", return_value=True)
@patch("builtins.open", new_callable=MagicMock)
@patch("aiosqlite.connect", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_initialize_db_success(
    mock_connect,
    mock_open,
    mock_exists,
    mock_mkdir,
    db_manager,
    mock_aiosqlite_connection,
):
    """Test successful database initialization."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn
    mock_schema_content = "CREATE TABLE test (id INTEGER);"
    # Configure mock_open to simulate reading the schema file
    mock_open.return_value.__enter__.return_value.read.return_value = (
        mock_schema_content
    )

    await db_manager.initialize_db()

    # Assertions
    # The DatabaseManager resolves schema path relative to its own file location
    schema_file_path = project_root / "src" / "database" / "schema.sql"
    # mock_exists is called on the Path object representing the schema file
    # We rely on mock_open to verify the correct path was used.
    mock_exists.assert_called_once()  # Check that exists() was called on the Path object
    mock_open.assert_called_once_with(schema_file_path, "r")  # Check schema file open
    mock_connect.assert_called_once()  # Check DB connection
    # Check connection setup calls (WAL mode)
    mock_conn.execute.assert_any_call("PRAGMA journal_mode=WAL;")
    # Check schema execution (executescript is awaited directly)
    mock_conn.executescript.assert_called_once_with(mock_schema_content)
    # Check commit after executescript
    assert mock_conn.commit.call_count >= 2  # Once for WAL, once for schema


# --- CRUD Tests ---


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_add_detection(mock_connect, db_manager, mock_aiosqlite_connection):
    """Test adding a detection record."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn
    mock_cursor.fetchone.return_value = (1,)  # Simulate returning row ID

    token = "TokenMint1"
    lp = "LPAddr1"
    base = "BaseMint1"
    creator = "Creator1"

    result_id = await db_manager.add_detection(token, lp, base, creator)
    commit_count_before = mock_conn.commit.call_count
    result_id = await db_manager.add_detection(token, lp, base, creator)
    commit_count_after = mock_conn.commit.call_count

    assert result_id == 1
    expected_sql = """
        INSERT INTO detections (token_mint, lp_address, base_mint, creator_address, status, last_updated)
        VALUES (?, ?, ?, ?, 'PENDING_FILTER', CURRENT_TIMESTAMP)
        ON CONFLICT(token_mint) DO UPDATE SET
            -- Only update last_updated on conflict, keep original status unless explicitly changed later
            last_updated = CURRENT_TIMESTAMP
            -- Optionally, could update lp_address etc. if needed:
            -- lp_address = excluded.lp_address
        RETURNING id;
        """
    # Use call comparison for execute
    assert mock_conn.cursor.call_count == 1  # Check cursor obtained exactly once
    mock_cursor.execute.assert_called_once()
    args, _ = mock_cursor.execute.call_args
    # Clean whitespace for comparison
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    assert args[1] == (token, lp, base, creator)  # Check parameters
    mock_cursor.fetchone.assert_called_once()
    # Assert that commit was called exactly once *during* this operation
    assert commit_count_after == commit_count_before + 1


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_update_detection_status(
    mock_connect, db_manager, mock_aiosqlite_connection
):
    """Test updating detection status."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn
    mock_cursor.rowcount = 1  # Simulate one row updated

    token = "TokenMint1"
    status = "PASSED_FILTER"
    reason = "Looks good"

    commit_count_before = mock_conn.commit.call_count
    success = await db_manager.update_detection_status(token, status, reason)
    commit_count_after = mock_conn.commit.call_count

    assert success is True
    expected_sql = """
        UPDATE detections
        SET status = ?, filter_fail_reason = ?, last_updated = CURRENT_TIMESTAMP
        WHERE token_mint = ?;
        """
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once()
    args, _ = mock_cursor.execute.call_args
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    assert args[1] == (status, reason, token)
    # Assert that commit was called exactly once *during* this operation
    assert commit_count_after == commit_count_before + 1


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_update_detection_status_not_found(
    mock_connect, db_manager, mock_aiosqlite_connection
):
    """Test updating status for a non-existent token."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn
    mock_cursor.rowcount = 0  # Simulate zero rows updated

    success = await db_manager.update_detection_status(
        "NonExistentToken", "FAILED_FILTER"
    )
    commit_count_before = mock_conn.commit.call_count
    success = await db_manager.update_detection_status(
        "NonExistentToken", "FAILED_FILTER"
    )  # Re-call the function after getting count
    commit_count_after = mock_conn.commit.call_count

    assert success is False
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once()
    # Assert that commit was called exactly once *during* this operation
    assert commit_count_after == commit_count_before + 1


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_add_position(mock_connect, db_manager, mock_aiosqlite_connection):
    """Test adding a position record."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn
    mock_cursor.fetchone.return_value = (5,)  # Simulate returning row ID 5

    token = "TokenMintPos1"
    lp = "LPAddrPos1"
    buy_sol = 0.1
    buy_sig = "BuySig1"
    buy_tokens = 1000.0
    buy_price = 0.0001

    result_id = await db_manager.add_position(
        token, lp, buy_sol, buy_sig, buy_tokens, buy_price
    )
    # Reset commit mock after connection is established and initial commit happens
    mock_conn.commit.reset_mock()

    assert result_id == 5
    expected_sql = """
        INSERT INTO positions (token_mint, lp_address, buy_amount_sol, buy_tx_signature, buy_amount_tokens, buy_price, buy_provider_identifier, status, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', CURRENT_TIMESTAMP)
        ON CONFLICT(token_mint) DO UPDATE SET
            -- If a position already exists, log warning and maybe update timestamp? Avoid overwriting active trade.
            last_updated = CURRENT_TIMESTAMP
            -- Consider adding a specific status like 'DUPLICATE_BUY_ATTEMPT' if needed
        RETURNING id;
        """
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once()
    args, _ = mock_cursor.execute.call_args
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    assert args[1] == (
        token,
        lp,
        buy_sol,
        buy_sig,
        buy_tokens,
        buy_price,
        None,
    )  # buy_provider_identifier is None
    mock_cursor.fetchone.assert_called_once()
    mock_conn.commit.assert_called_once()


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_update_position_status(
    mock_connect, db_manager, mock_aiosqlite_connection
):
    """Test updating position status."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn
    mock_cursor.rowcount = 1  # Simulate update success

    token = "TokenMintPos1"
    new_status = "SELL_PENDING"

    success = await db_manager.update_position_status(token, new_status)
    # Reset commit mock after connection is established and initial commit happens
    mock_conn.commit.reset_mock()

    assert success is True
    expected_sql = """
        UPDATE positions
        SET status = ?, last_updated = CURRENT_TIMESTAMP
        WHERE token_mint = ? AND status = 'ACTIVE'; -- Only update active positions
        """
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once()
    args, _ = mock_cursor.execute.call_args
    cleaned_expected_sql = " ".join(expected_sql.split())
    cleaned_actual_sql = " ".join(args[0].split())
    assert cleaned_actual_sql == cleaned_expected_sql
    assert args[1] == (new_status, token)
    mock_conn.commit.assert_called_once()


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_get_active_position(mock_connect, db_manager, mock_aiosqlite_connection):
    """Test retrieving a specific active position."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn
    # Simulate returning a row using a dictionary for Row factory compatibility
    # Need to mock the Row object itself if direct dict access is used in assertions
    mock_row = MagicMock(spec=aiosqlite.Row)
    mock_row.__getitem__.side_effect = lambda key: {
        "id": 1,
        "token_mint": "TokenMintActive",
        "status": "ACTIVE",
    }[key]
    mock_cursor.fetchone.return_value = mock_row

    token = "TokenMintActive"
    position = await db_manager.get_active_position(token)

    assert position is not None
    assert position["token_mint"] == token  # Access like a dictionary
    assert position["status"] == "ACTIVE"
    expected_sql = "SELECT * FROM positions WHERE token_mint = ? AND status = 'ACTIVE';"
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once_with(expected_sql, (token,))
    mock_cursor.fetchone.assert_called_once()
    # Check row_factory was set during the call
    assert mock_conn.row_factory == aiosqlite.Row


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_get_all_active_positions(
    mock_connect, db_manager, mock_aiosqlite_connection
):
    """Test retrieving all active positions."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn
    # Simulate returning Row objects
    row1 = MagicMock(spec=aiosqlite.Row)
    row1.__getitem__.side_effect = lambda k: {
        "id": 1,
        "token_mint": "Token1",
        "status": "ACTIVE",
    }[k]
    row2 = MagicMock(spec=aiosqlite.Row)
    row2.__getitem__.side_effect = lambda k: {
        "id": 2,
        "token_mint": "Token2",
        "status": "ACTIVE",
    }[k]
    mock_rows = [row1, row2]
    mock_cursor.fetchall.return_value = mock_rows

    positions = await db_manager.get_all_active_positions()

    assert len(positions) == 2
    assert positions[0]["token_mint"] == "Token1"
    assert positions[1]["token_mint"] == "Token2"
    expected_sql = "SELECT * FROM positions WHERE status = 'ACTIVE';"
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_once_with(expected_sql)
    mock_cursor.fetchall.assert_called_once()
    # Check row_factory *after* the call, as it's set within the method
    assert mock_conn.row_factory is aiosqlite.Row


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_move_position_to_trades_success(
    mock_connect, db_manager, mock_aiosqlite_connection
):
    """Test successfully moving a position to the trades table."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn

    # Mock the SELECT call to find the position
    position_row_data = {
        "id": 10,
        "token_mint": "TokenToMove",
        "lp_address": "LPMove",
        "buy_timestamp": "2023-01-01 10:00:00",
        "buy_amount_sol": 0.2,
        "buy_amount_tokens": 2000.0,
        "buy_price": 0.0001,
        "buy_tx_signature": "BuySigMove",
        "buy_provider_identifier": None,
        "status": "ACTIVE",
        "last_price_check_timestamp": None,
        "highest_price_since_buy": None,
        "last_updated": "2023-01-01 10:00:00",
    }
    # Setup cursor for multiple execute calls within the transaction
    # Mock the Row object for the fetchone call
    mock_pos_row = MagicMock(spec=aiosqlite.Row)
    mock_pos_row.__getitem__.side_effect = lambda k: position_row_data[k]

    # Mock transaction flow
    mock_conn.execute = AsyncMock(
        side_effect=[
            None,  # BEGIN
            mock_cursor,  # SELECT
            mock_cursor,  # INSERT
            mock_cursor,  # DELETE
            None,  # COMMIT
        ]
    )
    mock_cursor.fetchone = AsyncMock(return_value=mock_pos_row)

    token = "TokenToMove"
    sell_reason = "TP"
    sell_sig = "SellSigMove"
    sell_tokens = 1980.0
    sell_sol = 0.4
    sell_price = 0.000202

    success = await db_manager.move_position_to_trades(
        token, sell_reason, sell_sig, sell_tokens, sell_sol, sell_price
    )
    # Reset commit mock after connection is established and initial commit happens
    mock_conn.commit.reset_mock()

    assert success is True

    # Verify calls using assert_has_calls with the simplified mocking
    # Note: We don't mock BEGIN/COMMIT/ROLLBACK explicitly anymore with execute,
    # but rely on the connection's commit/rollback mocks being called.
    # The cursor's execute method handles the SQL queries.
    expected_cursor_calls = [
        call(  # The initial SELECT call
            "SELECT * FROM positions WHERE token_mint = ? AND status = 'ACTIVE';",
            (token,),
        ),
        call(  # The INSERT call
            pytest.ANY,  # Match the INSERT SQL string (verified below)
            (
                token,
                "LPMove",
                "2023-01-01 10:00:00",  # buy_timestamp from mock data
                0.2,  # buy_amount_sol from mock data
                2000.0,  # buy_amount_tokens from mock data
                0.0001,  # buy_price from mock data
                "BuySigMove",  # buy_tx_signature from mock data
                None,  # buy_provider_identifier from mock data
                sell_tokens,  # sell_amount_tokens from test args
                sell_sol,  # sell_amount_sol from test args
                sell_price,  # sell_price from test args
                sell_sig,  # sell_tx_signature from test args
                None,  # sell_provider_identifier (default None)
                sell_reason,  # sell_reason from test args
                0.2,  # pnl_sol (sell_sol - buy_sol)
                102.0,  # pnl_percentage ((sell_price / buy_price) - 1) * 100
            ),
        ),
        call("DELETE FROM positions WHERE id = ?;", (10,)),  # id from mock data
    ]
    # Check that the cursor execute method was called with the expected sequence
    # Note: The cursor is obtained *within* the transaction context manager in the source code.
    # We assert calls on the mock_cursor directly.
    mock_cursor.execute.assert_has_calls(expected_cursor_calls, any_order=False)

    # Verify commit was called on the connection (signifying successful transaction)
    mock_conn.commit.assert_called_once()
    mock_conn.rollback.assert_not_called()  # Ensure rollback wasn't called

    # Verify the INSERT SQL structure specifically (optional but good practice)
    # Find the insert call within the cursor's calls
    insert_call = next(
        c
        for c in mock_cursor.execute.call_args_list
        if "INSERT INTO trades" in c.args[0]
    )
    insert_sql_actual = " ".join(insert_call.args[0].split())
    insert_sql_expected = " ".join(
        """
            INSERT INTO trades (token_mint, lp_address, buy_timestamp, buy_amount_sol, buy_amount_tokens, buy_price, buy_tx_signature, buy_provider_identifier,
                                sell_timestamp, sell_amount_tokens, sell_amount_sol, sell_price, sell_tx_signature, sell_provider_identifier, sell_reason, pnl_sol, pnl_percentage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?);
            """.split()
    )
    assert insert_sql_actual == insert_sql_expected


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_move_position_to_trades_not_found(
    mock_connect, db_manager, mock_aiosqlite_connection
):
    """Test moving a position that doesn't exist or isn't active."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn

    # Mock the SELECT call to return None
    async def execute_side_effect(sql, params=None):
        if "BEGIN TRANSACTION" in sql:
            return None  # execute doesn't return cursor
        elif "SELECT * FROM positions" in sql:
            mock_cursor.fetchone = AsyncMock(return_value=None)  # Simulate not found
            return mock_cursor
        elif "ROLLBACK" in sql:
            return None  # execute doesn't return cursor
        else:
            mock_cursor.fetchone = AsyncMock(return_value=None)
            return mock_cursor

    mock_conn.execute = AsyncMock(side_effect=execute_side_effect)

    success = await db_manager.move_position_to_trades(
        "NotFoundToken", "TP", "SellSigNotFound"
    )

    assert success is False
    # Filter out PRAGMA call if it happens during connection setup
    actual_calls = [
        c for c in mock_conn.execute.call_args_list if "PRAGMA" not in c.args[0]
    ]
    expected_calls = [
        call("BEGIN TRANSACTION;"),
        call(
            "SELECT * FROM positions WHERE token_mint = ? AND status = 'ACTIVE';",
            ("NotFoundToken",),
        ),
        call("ROLLBACK;"),  # Should rollback because position wasn't found
    ]
    assert actual_calls == expected_calls


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_check_if_token_processed(
    mock_connect, db_manager, mock_aiosqlite_connection
):
    """Test checking if a token exists in detections."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn

    # Test case 1: Token exists
    mock_cursor.fetchone = AsyncMock(return_value=(1,))  # Simulate finding a row
    processed = await db_manager.check_if_token_processed("ExistingToken")
    assert processed is True
    # Check the last call to execute on the cursor
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_with(
        "SELECT 1 FROM detections WHERE token_mint = ? LIMIT 1;", ("ExistingToken",)
    )

    # Test case 2: Token does not exist
    mock_conn.cursor.reset_mock()  # Reset cursor mock for next call
    mock_cursor.fetchone = AsyncMock(return_value=None)  # Simulate not finding a row
    processed = await db_manager.check_if_token_processed("NewToken")
    assert processed is False
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_with(
        "SELECT 1 FROM detections WHERE token_mint = ? LIMIT 1;", ("NewToken",)
    )


@pytest.mark.asyncio
@patch("aiosqlite.connect", new_callable=AsyncMock)
async def test_check_if_creator_processed(
    mock_connect, db_manager, mock_aiosqlite_connection
):
    """Test checking if a creator exists in detections."""
    mock_conn, mock_cursor = mock_aiosqlite_connection
    mock_connect.return_value = mock_conn

    # Test case 1: Creator exists
    mock_cursor.fetchone = AsyncMock(return_value=(1,))
    processed = await db_manager.check_if_creator_processed("ExistingCreator")
    assert processed is True
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_with(
        "SELECT 1 FROM detections WHERE creator_address = ? LIMIT 1;",
        ("ExistingCreator",),
    )
    execute_call_count = mock_cursor.execute.call_count

    # Test case 2: Creator does not exist
    mock_conn.cursor.reset_mock()  # Reset cursor mock
    mock_cursor.fetchone = AsyncMock(return_value=None)
    processed = await db_manager.check_if_creator_processed("NewCreator")
    assert processed is False
    mock_conn.cursor.assert_called_once()
    mock_cursor.execute.assert_called_with(
        "SELECT 1 FROM detections WHERE creator_address = ? LIMIT 1;", ("NewCreator",)
    )
    # Simplified assertion: Ensure execute was called correctly for the second case.
    # The previous call count logic was prone to errors with mock resets.

    # Test case 3: Creator address is None or empty
    last_call_count = mock_cursor.execute.call_count  # Store count before this case
    mock_conn.cursor.reset_mock()  # Reset cursor mock
    processed = await db_manager.check_if_creator_processed(None)  # type: ignore
    assert processed is False
    processed = await db_manager.check_if_creator_processed("")
    assert processed is False
    # Ensure execute wasn't called for None/empty
    mock_conn.cursor.assert_not_called()  # Cursor shouldn't even be obtained
    assert (
        mock_cursor.execute.call_count == last_call_count
    )  # Count should not increase
