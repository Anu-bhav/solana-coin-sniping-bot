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
async def _get_connection(self):
    """Acquire a database connection from the pool."""
    if not self._connection_pool:
        self._connection_pool = await aiosqlite.connect(
            database=self.db_path,
            timeout=Config.DB_TIMEOUT,
            check_same_thread=False,
            pool_size=Config.DB_POOL_SIZE,
        )
        self._connection_pool.row_factory = aiosqlite.Row

    async with self._connection_pool.cursor() as cursor:
        yield cursor

    async def move_position_to_trades(
        self, position_id: str, trade_data: Dict[str, Any]
    ) -> bool:
        """
        Atomically move a position to trades table with transaction rollback.

        Args:
            position_id: Unique identifier for the position
            trade_data: Dictionary of trade details

        Returns:
            bool: True if successful, False on failure
        """
        async with self._get_connection() as conn:
            try:
                # Validate position exists
                await conn.execute("BEGIN IMMEDIATE")
                position = await conn.execute(
                    "SELECT * FROM positions WHERE id = ?", (position_id,)
                )
                if not await position.fetchone():
                    logger.error(f"Position {position_id} not found")
                    return False

                # Insert trade
                await conn.execute(
                    """INSERT INTO trades
                    (position_id, amount, price, timestamp)
                    VALUES (?, ?, ?, ?)""",
                    (
                        position_id,
                        trade_data["amount"],
                        trade_data["price"],
                        trade_data["timestamp"],
                    ),
                )

                # Delete position
                await conn.execute("DELETE FROM positions WHERE id = ?", (position_id,))

                await conn.connection.commit()
                return True
            except aiosqlite.Error as e:
                logger.error(f"Transaction failed: {str(e)}")
                await conn.connection.rollback()
                return False

    async def check_if_creator_processed(
        self, creator_address: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a creator has been processed with associated trades.

        Args:
            creator_address: Solana creator address

        Returns:
            Dict with processed status and trade count, None if error
        """
        async with self._get_connection() as conn:
            try:
                result = await conn.execute(
                    """SELECT pc.*, COUNT(t.id) as trade_count
                    FROM processed_creators pc
                    LEFT JOIN trades t ON pc.creator_address = t.creator_address
                    WHERE pc.creator_address = ?
                    GROUP BY pc.creator_address""",
                    (creator_address,),
                )
                return await result.fetchone()
            except aiosqlite.Error as e:
                logger.error(f"Creator check failed: {str(e)}")
                return None

    @classmethod
    async def create_pool(cls):
        """Create connection pool from configuration."""
        return await aiosqlite.connect(
            database=Config.DATABASE_URL,
            timeout=Config.DB_TIMEOUT,
            check_same_thread=False,
            pool_size=Config.DB_POOL_SIZE,
        )

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
