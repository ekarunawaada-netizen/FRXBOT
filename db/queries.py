"""
db/queries.py — Signal Logging & Whitelist Queries (SQLite)

All queries now execute against the local SQLite database via
db/connection.py's async wrapper. No network I/O, no timeouts.
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from db.connection import get_db_connection

logger = logging.getLogger(__name__)


async def is_user_whitelisted(user_id: int) -> bool:
    """
    Checks if a user is in the whitelist_users table and has an active status.

    Args:
        user_id: The Telegram User ID.

    Returns:
        True if user exists and is active, False otherwise.
    """
    try:
        async with get_db_connection() as conn:
            is_active = await conn.fetchval(
                "SELECT is_active FROM whitelist_users WHERE user_id = ?;",
                user_id
            )
            return bool(is_active)
    except Exception as e:
        logger.error(f"Error checking whitelist for user {user_id}: {e}")
        return False


async def log_signal(
    user_id: int,
    pair: str,
    timeframe: str,
    direction: str,
    entry_price: float,
    sl_price: float,
    tp1_price: float,
    tp2_price: float,
    lot_size: float,
    atr_value: float,
    signal_source: str,
    ai_confidence: Optional[float] = None,
    ai_reasoning: Optional[str] = None
) -> Optional[int]:
    """
    Logs a generated signal into the local SQLite signals_log table.

    Args:
        user_id: Telegram User ID.
        pair: Currency pair (e.g. "XAUUSD").
        timeframe: Signal timeframe (e.g. "H1", "M5").
        direction: Signal direction ("LONG" | "SHORT").
        entry_price: Recommended entry price.
        sl_price: Recommended stop loss price.
        tp1_price: Recommended take profit 1 price.
        tp2_price: Recommended take profit 2 price.
        lot_size: Recommended lot size.
        atr_value: Calculated ATR value.
        signal_source: Source of the signal ("PUSH" | "PULL").
        ai_confidence: Optional AI model confidence score.
        ai_reasoning: Optional reasoning behind the signal.

    Returns:
        The row ID of the inserted log record, or None if logging failed.
    """
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        async with get_db_connection() as conn:
            await conn.execute(
                """
                INSERT INTO signals_log (
                    user_id, symbol, mode, timeframe, direction,
                    entry_price, sl_price, tp1_price, tp2_price,
                    lot_size, atr_value, signal_source,
                    ai_confidence, ai_reasoning, outcome, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?);
                """,
                str(user_id),
                pair.upper(),
                timeframe,       # mode column stores timeframe context
                timeframe,
                direction.upper(),
                entry_price,
                sl_price,
                tp1_price,
                tp2_price,
                lot_size,
                atr_value,
                signal_source.upper(),
                ai_confidence,
                ai_reasoning,
                timestamp
            )

            # Retrieve the last inserted row ID
            row_id = await conn.fetchval("SELECT last_insert_rowid();")
            logger.info(f"Signal logged for user {user_id} on {pair} (row {row_id}).")
            return row_id

    except Exception as e:
        logger.error(f"Error logging signal for user {user_id} on {pair}: {e}")
        return None
