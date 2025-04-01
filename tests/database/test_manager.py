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
async def db_manager(mock_config):
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
    return manager


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
    mock_conn.cursor = AsyncMock(return_value=mock_cursor)
    mock_conn.execute = AsyncMock(return_value=mock_cursor)  # execute returns cursor
    mock_conn.executescript = AsyncMock(
        return_value=mock_cursor
    )  # executescript returns cursor
    mock_conn.commit = AsyncMock()
    mock_conn.rollback = AsyncMock()
    mock_conn.close = AsyncMock()
    # Add row_factory attribute
    mock_conn.row_factory = None

    # Make cursor awaitable if used in 'async with conn.cursor()'
    async def cursor_aenter(self):
        return self
