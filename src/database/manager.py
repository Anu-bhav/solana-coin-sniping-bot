# src/database/manager.py

import aiosqlite
import logging
import os
import asyncio  # Added for sleep in retry
from pathlib import Path
from typing import Optional, List, Tuple, Any

# Assuming AppConfig is defined in src.core.models and includes database settings
from src.core.models import AppConfig

# Configure logging
# Use logger from core setup if available, otherwise basic config
try:
    from src.core.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages asynchronous interactions with the SQLite database.
    Handles connection, schema initialization, and CRUD operations.
    """

    def __init__(self, config: AppConfig):
        """
        Initializes the DatabaseManager with application configuration.

        Args:
            config: The validated application configuration object.
        """
        self.config = config
        self.db_path: Optional[Path] = None
        self.connection: Optional[aiosqlite.Connection] = None

        # Determine the correct database file path based on environment
        db_config = config.database
        if config.general.app_env == "production":
            db_filename = db_config.prod_db_file
        else:
            db_filename = db_config.dev_db_file

        if db_filename:
            # Construct the full path relative to the project root or a defined base path
            # Assuming the script runs from the project root or db_path is relative to it
            try:
                project_root = (
                    Path(__file__).resolve().parents[2]
                )  # Adjust index if structure changes
                self.db_path = project_root / db_config.db_path / db_filename
                logger.info(f"Database path set to: {self.db_path}")
            except IndexError:
                logger.error(
                    "Could not determine project root. Place manager.py appropriately or adjust path logic."
                )
                self.db_path = (
                    Path(db_config.db_path) / db_filename
                )  # Fallback to relative path
                logger.warning(
                    f"Using potentially incorrect relative database path: {self.db_path}"
                )

        else:
            logger.error("Database filename is not configured.")
            # Potentially raise an error or handle this case appropriately

    async def _get_connection(self) -> aiosqlite.Connection:
        """Establishes and returns the database connection."""
        if self.connection is None or not self._is_connection_active():
            if not self.db_path:
                raise ValueError("Database path is not configured.")
            try:
                # Ensure the directory exists
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.connection = await aiosqlite.connect(
                    self.db_path, timeout=10.0
                )  # Add timeout
                # Enable foreign key constraints if needed (optional)
                # await self.connection.execute("PRAGMA foreign_keys = ON;")
                # await self.connection.commit()
                # Set WAL mode for better concurrency
                await self.connection.execute("PRAGMA journal_mode=WAL;")
                await self.connection.commit()
                logger.info(f"Successfully connected to database: {self.db_path}")
            except aiosqlite.Error as e:
                logger.error(
                    f"Error connecting to database {self.db_path}: {e}", exc_info=True
                )
                self.connection = None  # Ensure connection is None on failure
                raise
        return self.connection

    def _is_connection_active(self) -> bool:
        """Checks if the connection is likely active."""
        if not self.connection:
            return False
        # aiosqlite doesn't have a simple is_connected property.
        # Checking if the object exists is the primary check after close_connection sets it to None.
        # A more complex check could involve trying a PRAGMA, but adds overhead.
        return True

    async def close_connection(self):
        """Closes the database connection if it's open."""
        if self.connection:
            try:
                await self.connection.close()
                logger.info("Database connection closed.")
            except aiosqlite.Error as e:
                logger.error(f"Error closing database connection: {e}", exc_info=True)
            finally:
                self.connection = None  # Ensure connection is set to None

    async def initialize_db(self):
        """
        Initializes the database by creating tables based on schema.sql
        if they don't already exist.
        """
        if not self.db_path:
            logger.error("Cannot initialize database: path not configured.")
            return

        # Look for schema relative to this file's directory
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            logger.error(f"Database schema file not found at: {schema_path}")
            return

        try:
            with open(schema_path, "r") as f:
                schema_sql = f.read()
        except IOError as e:
            logger.error(f"Error reading schema file {schema_path}: {e}", exc_info=True)
            return

        retries = 3
        for attempt in range(retries):
            try:
                conn = await self._get_connection()
                # Correct usage: executescript is awaited directly
                await conn.executescript(schema_sql)
                await conn.commit()
                logger.info(
                    "Database schema initialized successfully (tables created if not exist)."
                )
                return  # Success
            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e) and attempt < retries - 1:
                    logger.warning(
                        f"Database locked during initialization, retrying ({attempt + 1}/{retries})..."
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(
                        f"Error initializing database schema: {e}", exc_info=True
                    )
                    raise  # Re-raise final error
            except aiosqlite.Error as e:
                logger.error(f"Error initializing database schema: {e}", exc_info=True)
                raise  # Re-raise other errors

    # --- CRUD Operations ---

    async def add_detection(
        self,
        token_mint: str,
        lp_address: str,
        base_mint: str,
        creator_address: Optional[str] = None,
    ) -> Optional[int]:
        """
        Adds a new detection record or updates status if it already exists (UPSERT).
        Defaults status to 'PENDING_FILTER'.

        Args:
            token_mint: The mint address of the detected token.
            lp_address: The liquidity pool address.
            base_mint: The base token mint address (e.g., SOL).
            creator_address: The potential creator address (optional).

        Returns:
            The row ID of the inserted/updated record, or None on failure.
        """
        sql = """
        INSERT INTO detections (token_mint, lp_address, base_mint, creator_address, status, last_updated)
        VALUES (?, ?, ?, ?, 'PENDING_FILTER', CURRENT_TIMESTAMP)
        ON CONFLICT(token_mint) DO UPDATE SET
            -- Only update last_updated on conflict, keep original status unless explicitly changed later
            last_updated = CURRENT_TIMESTAMP
            -- Optionally, could update lp_address etc. if needed:
            -- lp_address = excluded.lp_address
        RETURNING id;
        """
        try:
            conn = await self._get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(
                    sql, (token_mint, lp_address, base_mint, creator_address)
                )
                result = await cursor.fetchone()
            await conn.commit()
            logger.debug(
                f"Detection added/updated for {token_mint}, ID: {result[0] if result else 'N/A'}"
            )
            return result[0] if result else None
        except aiosqlite.Error as e:
            logger.error(f"Error in add_detection for {token_mint}: {e}", exc_info=True)
            return None

    async def update_detection_status(
        self, token_mint: str, status: str, reason: Optional[str] = None
    ) -> bool:
        """
        Updates the status and optional reason for a detected token.

        Args:
            token_mint: The mint address of the token to update.
            status: The new status (e.g., PASSED_FILTER, FAILED_FILTER).
            reason: The reason for failure (optional).

        Returns:
            True if the update was successful (at least one row affected), False otherwise.
        """
        sql = """
        UPDATE detections
        SET status = ?, filter_fail_reason = ?, last_updated = CURRENT_TIMESTAMP
        WHERE token_mint = ?;
        """
        try:
            conn = await self._get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(sql, (status, reason, token_mint))
                rowcount = cursor.rowcount
            await conn.commit()
            if rowcount > 0:
                logger.debug(f"Updated detection status for {token_mint} to {status}")
                return True
            else:
                logger.warning(
                    f"Attempted to update status for non-existent token_mint: {token_mint}"
                )
                return False
        except aiosqlite.Error as e:
            logger.error(
                f"Error updating detection status for {token_mint}: {e}", exc_info=True
            )
            return False

    def _validate_db_config(self) -> None:
        """Validate database configuration during initialization."""
        db_config = self.config.database
        if not db_config.db_path or not isinstance(db_config.db_path, str):
            raise ValueError("Invalid database path in configuration")

        env = self.config.general.app_env
        if env not in ("production", "development", "testing"):
            raise ValueError(f"Invalid environment '{env}' in configuration")

    def _sql_retry_decorator(self, max_retries: int = 3):
        """Decorator for SQL operations with retry logic."""

        def decorator(func):
            async def wrapper(*args, **kwargs):
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except aiosqlite.OperationalError as e:
                        if "locked" not in str(e) or attempt == max_retries - 1:
                            raise
                        wait = 0.5 * (attempt + 1)
                        logger.warning(f"DB locked, retrying in {wait}s...")
                        await asyncio.sleep(wait)
                return None

            return wrapper

        return decorator

    @_sql_retry_decorator()
    async def add_position(
        self,
        token_mint: str,
        lp_address: str,
        buy_amount_sol: float,
        buy_tx_signature: str,
        buy_amount_tokens: Optional[float] = None,
        buy_price: Optional[float] = None,
        buy_provider_identifier: Optional[str] = None,
    ) -> Optional[int]:
        """UPSERT position with transaction support."""
        sql = """
        INSERT INTO positions (token_mint, lp_address, buy_amount_sol,
            buy_tx_signature, buy_amount_tokens, buy_price,
            buy_provider_identifier, status, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', CURRENT_TIMESTAMP)
        ON CONFLICT(token_mint) DO UPDATE SET
            last_updated = CURRENT_TIMESTAMP
        RETURNING id;
        """
        try:
            async with await self._get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        sql,
                        (
                            token_mint,
                            lp_address,
                            buy_amount_sol,
                            buy_tx_signature,
                            buy_amount_tokens,
                            buy_price,
                            buy_provider_identifier,
                        ),
                    )
                    result = await cursor.fetchone()
                    await conn.commit()
                    return result[0] if result else None
        except aiosqlite.IntegrityError as e:
            logger.warning(f"Position conflict for {token_mint}: {e}")
            return None
        except aiosqlite.Error as e:
            logger.error(f"Position error: {e}")
            return None

    async def update_position_status(self, token_mint: str, status: str) -> bool:
        """
        Updates the status of an active position.

        Args:
            token_mint: The mint address of the position to update.
            status: The new status (e.g., SELL_PENDING, SELL_FAILED).

        Returns:
            True if successful (at least one row affected), False otherwise.
        """
        sql = """
        UPDATE positions
        SET status = ?, last_updated = CURRENT_TIMESTAMP
        WHERE token_mint = ? AND status = 'ACTIVE'; -- Only update active positions
        """
        try:
            conn = await self._get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(sql, (status, token_mint))
                rowcount = cursor.rowcount
            await conn.commit()
            if rowcount > 0:
                logger.debug(f"Updated position status for {token_mint} to {status}")
                return True
            else:
                logger.warning(
                    f"Attempted to update status for non-active/non-existent position: {token_mint}"
                )
                return False
        except aiosqlite.Error as e:
            logger.error(
                f"Error updating position status for {token_mint}: {e}", exc_info=True
            )
            return False

    async def get_active_position(self, token_mint: str) -> Optional[aiosqlite.Row]:
        """
        Retrieves details for a specific active position as a Row object.

        Args:
            token_mint: The token mint address.

        Returns:
            An aiosqlite.Row object containing position details, or None if not found or not active.
        """
        sql = "SELECT * FROM positions WHERE token_mint = ? AND status = 'ACTIVE';"
        try:
            conn = await self._get_connection()
            conn.row_factory = aiosqlite.Row  # Return rows as dictionary-like objects
            async with conn.cursor() as cursor:
                await cursor.execute(sql, (token_mint,))
                result = await cursor.fetchone()
            return result
        except aiosqlite.Error as e:
            logger.error(
                f"Error getting active position for {token_mint}: {e}", exc_info=True
            )
            return None
        finally:
            if conn:
                conn.row_factory = None  # Reset row factory

    async def get_all_active_positions(self) -> List[aiosqlite.Row]:
        """
        Retrieves details for all active positions as Row objects.

        Returns:
            A list of aiosqlite.Row objects, each containing position details. Empty list if none found.
        """
        sql = "SELECT * FROM positions WHERE status = 'ACTIVE';"
        try:
            conn = await self._get_connection()
            conn.row_factory = aiosqlite.Row
            async with conn.cursor() as cursor:
                await cursor.execute(sql)
                results = await cursor.fetchall()
            return results
        except aiosqlite.Error as e:
            logger.error(f"Error getting all active positions: {e}", exc_info=True)
            return []
        finally:
            if conn:
                conn.row_factory = None

    async def move_position_to_trades(
        self,
        token_mint: str,
        sell_reason: str,
        sell_tx_signature: str,
        sell_amount_tokens: Optional[float] = None,
        sell_amount_sol: Optional[float] = None,
        sell_price: Optional[float] = None,
        sell_provider_identifier: Optional[str] = None,
    ) -> bool:
        """
        Atomically moves a closed position to the trades table with transaction support.

        Args:
            token_mint: The mint address of the token position
            sell_reason: Reason for closing the position
            sell_tx_signature: Transaction signature of the sell order
            sell_amount_tokens: Amount of tokens sold (optional)
            sell_amount_sol: Amount of SOL received (optional)
            sell_price: Price per token in SOL (optional)
            sell_provider_identifier: Provider ID for the sell order (optional)

        Returns:
            True if successful, False otherwise
        """
        retries = 3
        for attempt in range(retries):
            try:
                async with await self._get_connection() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("BEGIN TRANSACTION")

                        # Get active position
                        await cursor.execute(
                            """SELECT * FROM positions
                            WHERE token_mint = ? AND status = 'ACTIVE'
                            FOR UPDATE""",
                            (token_mint,),
                        )
                        position = await cursor.fetchone()

                        if not position:
                            logger.warning(f"No active position for {token_mint}")
                            await cursor.execute("ROLLBACK")
                            return False

                        # Insert into trades with all position data
                        await cursor.execute(
                            """INSERT INTO trades (
                                token_mint, lp_address, buy_amount_sol, buy_tx_signature,
                                buy_amount_tokens, buy_price, buy_provider_identifier,
                                sell_amount_tokens, sell_amount_sol, sell_price,
                                sell_provider_identifier, sell_tx_signature, sell_reason,
                                status, created_at, closed_at
                            ) VALUES (
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                'CLOSED', ?, CURRENT_TIMESTAMP
                            ) RETURNING id""",
                            (
                                position["token_mint"],
                                position["lp_address"],
                                position["buy_amount_sol"],
                                position["buy_tx_signature"],
                                position["buy_amount_tokens"],
                                position["buy_price"],
                                position["buy_provider_identifier"],
                                sell_amount_tokens,
                                sell_amount_sol,
                                sell_price,
                                sell_provider_identifier,
                                sell_tx_signature,
                                sell_reason,
                                position["last_updated"],
                            ),
                        )

                        # Delete from positions
                        await cursor.execute(
                            "DELETE FROM positions WHERE id = ?", (position["id"],)
                        )

                        await conn.commit()
                        logger.info(f"Moved {token_mint} to trades")
                        return True

            except aiosqlite.OperationalError as e:
                if "locked" in str(e) and attempt < retries - 1:
                    wait = 0.5 * (attempt + 1)
                    logger.warning(f"DB locked, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Move position failed: {e}", exc_info=True)
                return False
            except aiosqlite.Error as e:
                logger.error(f"Database error: {e}", exc_info=True)
                return False

    async def check_if_token_processed(self, token_mint: str) -> bool:
        """
        Checks if a token has already been processed (i.e., exists in detections table).

        Args:
            token_mint: The token mint address.

        Returns:
            True if the token exists in the detections table, False otherwise.
        """
        sql = "SELECT 1 FROM detections WHERE token_mint = ? LIMIT 1;"
        try:
            conn = await self._get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(sql, (token_mint,))
                result = await cursor.fetchone()
            return result is not None
        except aiosqlite.Error as e:
            logger.error(
                f"Error checking if token processed {token_mint}: {e}", exc_info=True
            )
            return False  # Assume not processed on error

    async def check_if_creator_processed(self, creator_address: str) -> bool:
        """
        Checks if a creator has already been processed in any detection.

        Args:
            creator_address: The creator's wallet address to check

        Returns:
            True if creator exists in detections table, False otherwise
        """
        if not creator_address:
            return False

        retries = 3
        sql = """SELECT 1 FROM detections
               WHERE creator_address = ?
               AND status NOT IN ('FAILED_FILTER', 'REJECTED')
               LIMIT 1;"""

        for attempt in range(retries):
            try:
                async with await self._get_connection() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(sql, (creator_address,))
                        result = await cursor.fetchone()
                        return bool(result)
            except aiosqlite.OperationalError as e:
                if "locked" in str(e) and attempt < retries - 1:
                    wait = 0.5 * (attempt + 1)
                    logger.warning(f"Database locked, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"Creator check failed: {e}", exc_info=True)
                return False
            except aiosqlite.Error as e:
                logger.error(f"Database error during creator check: {e}", exc_info=True)
                return False
