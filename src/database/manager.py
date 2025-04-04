import asyncpg
from typing import Optional, List, Dict


class DatabaseManager:
    """Manages database connections and operations for the sniping bot"""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: Optional[asyncpg.pool.Pool] = None

    async def connect(self):
        """Initialize connection pool"""
        self.pool = await asyncpg.create_pool(
            dsn=self.dsn, min_size=2, max_size=10, command_timeout=60
        )

    async def close(self):
        """Cleanup connection pool"""
        if self.pool:
            await self.pool.close()

    # CRUD Operations
    async def add_detection(
        self,
        token_mint: str,
        lp_address: str,
        base_mint: str,
        creator_address: Optional[str] = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO detections (token_mint, lp_address, base_mint, creator_address)
                    VALUES ($1, $2, $3, $4)
                """,
                    token_mint,
                    lp_address,
                    base_mint,
                    creator_address,
                )

    async def update_detection_status(
        self, token_mint: str, status: str, filter_fail_reason: Optional[str] = None
    ) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE detections 
                    SET status = $1, filter_fail_reason = $2
                    WHERE token_mint = $3
                """,
                    status,
                    filter_fail_reason,
                    token_mint,
                )

    async def add_position(
        self,
        token_mint: str,
        lp_address: str,
        buy_amount_sol: float,
        buy_amount_tokens: float,
        buy_price: float,
        buy_tx_signature: str,
        buy_provider_identifier: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
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
                """,
                    token_mint,
                    lp_address,
                    buy_amount_sol,
                    buy_amount_tokens,
                    buy_price,
                    buy_tx_signature,
                    buy_provider_identifier,
                )

    async def get_active_position(self, token_mint: str) -> Optional[Dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM positions 
                WHERE token_mint = $1 AND status = 'ACTIVE'
            """,
                token_mint,
            )
            return dict(row) if row else None

    async def get_all_active_positions(self) -> List[Dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM positions 
                WHERE status = 'ACTIVE'
                ORDER BY buy_timestamp DESC
            """
            )
            return [dict(row) for row in rows]

    async def check_if_token_processed(self, token_mint: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM detections
                    WHERE token_mint = $1 
                    AND status IN ('PASSED_FILTER', 'FAILED_FILTER', 'BUY_PENDING', 'BUY_FAILED')
                    
                    UNION ALL
                    
                    SELECT 1 FROM positions
                    WHERE token_mint = $1 
                    AND status IN ('ACTIVE', 'SELL_PENDING', 'SELL_FAILED')
                )
            """,
                token_mint,
            )
            return bool(result)
