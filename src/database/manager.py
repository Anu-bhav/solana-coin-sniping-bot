import aiosqlite
import logging
import os
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from config import Config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Managed database connections with connection pooling and atomic transactions."""

    def __init__(self):
        self.db_path: str = Config.DATABASE_URL
        self.pool_size: int = Config.DB_POOL_SIZE
        self._connection_pool = None

    @asynccontextmanager
    async def _get_connection(self) -> aiosqlite.Connection:
        """Get async connection from pool with transaction isolation."""
        if not self._connection_pool:
            self._connection_pool = await aiosqlite.connect(
                database=self.db_path,
                timeout=Config.DB_TIMEOUT,
                check_same_thread=False,
                pool_size=Config.DB_POOL_SIZE,
                isolation_level="IMMEDIATE",
            )
            self._connection_pool.row_factory = aiosqlite.Row

        async with self._connection_pool.cursor() as cursor:
            try:
                await cursor.execute("PRAGMA foreign_keys = ON")
                yield cursor
            finally:
                await cursor.close()

    async def move_position_to_trades(
        self, position_id: str, trade_data: Dict[str, Any]
    ) -> bool:
        """
        Atomically move a position to trades table with transaction rollback.

        Args:
            position_id: Unique identifier for the position
            trade_data: Dictionary containing:
                - amount: float
                - price: float
                - timestamp: int

        Returns:
            bool: True if successful, False on failure
        """
        required_fields = {"amount", "price", "timestamp"}
        if not required_fields.issubset(trade_data):
            logger.error(
                f"Missing required trade fields: {required_fields - trade_data.keys()}"
            )
            return False

        async with self._get_connection() as conn:
            try:
                await conn.execute("BEGIN IMMEDIATE")

                # Validate position exists and is in open state
                position = await conn.execute(
                    """SELECT id, status, creator_address FROM positions
                    WHERE id = ? AND status = ?
                    FOR UPDATE""",
                    (position_id, Config.OPEN_POSITION_STATUS),
                )
                pos_record = await position.fetchone()

                if not pos_record:
                    logger.error(f"Position {position_id} not found or not open")
                    await conn.rollback()
                    return False

                # Insert trade with parameterized query
                await conn.execute(
                    """INSERT INTO trades
                    (position_id, amount, price, timestamp, creator_address)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        position_id,
                        trade_data["amount"],
                        trade_data["price"],
                        trade_data["timestamp"],
                        pos_record["creator_address"],
                    ),
                )

                # Archive position using configured status
                await conn.execute(
                    """UPDATE positions SET status = ?
                    WHERE id = ?""",
                    (Config.CLOSED_POSITION_STATUS, position_id),
                )

                await conn.commit()
                return True
            except aiosqlite.Error as e:
                logger.error(f"Transaction failed: {str(e)} - Position: {position_id}")
                await conn.rollback()
                return False
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                await conn.rollback()
                return False

    async def check_if_creator_processed(
        self, creator_address: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check creator processing status with trade metadata.

        Args:
            creator_address: Base58 encoded Solana address

        Returns:
            Dictionary containing:
            - processed: bool
            - first_processed_at: Optional[int]
            - last_trade_at: Optional[int]
            - total_trades: int
            - total_volume: float
        """
        async with self._get_connection() as conn:
            try:
                result = await conn.execute(
                    """SELECT
                        pc.processed,
                        pc.processed_at AS first_processed_at,
                        MAX(t.timestamp) AS last_trade_at,
                        COUNT(t.id) AS total_trades,
                        COALESCE(SUM(t.amount * t.price), 0) AS total_volume
                    FROM processed_creators pc
                    LEFT JOIN trades t
                        ON pc.creator_address = t.creator_address
                        AND t.timestamp > ?  -- Configurable cutoff
                    WHERE pc.creator_address = ?
                    GROUP BY pc.creator_address
                    /*+ INDEX(pc processed_creators_address_idx) */""",
                    (Config.CREATOR_CUTOFF_TIMESTAMP, creator_address),
                )
                row = await result.fetchone()
                return dict(row) if row else None
            except aiosqlite.Error as e:
                logger.error(f"Creator check failed: {str(e)}")
                return None

    @classmethod
    async def create_pool(cls) -> None:
        """Initialize connection pool from environment configuration."""
        cls._connection_pool = await aiosqlite.connect(
            database=Config.DATABASE_URL,
            timeout=Config.DB_TIMEOUT,
            check_same_thread=Config.DB_CHECK_SAME_THREAD,
            pool_size=Config.DB_POOL_SIZE,
            isolation_level=Config.DB_ISOLATION_LEVEL,
            journal_mode=Config.DB_JOURNAL_MODE,
            cached_statements=Config.DB_STATEMENT_CACHE_SIZE,
            detect_types=Config.DB_DETECT_TYPES,
        )
        cls._connection_pool.row_factory = aiosqlite.Row

    async def close(self):
        """Close all database connections."""
        if self._connection_pool:
            await self._connection_pool.close()
            self._connection_pool = None


# Configuration validation
if not all([Config.DATABASE_URL, Config.DB_POOL_SIZE]):
    raise EnvironmentError(
        "Missing required database configuration values. "
        "Set DATABASE_URL and DB_POOL_SIZE in environment."
    )
