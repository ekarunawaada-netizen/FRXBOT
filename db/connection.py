"""
db/connection.py — Local SQLite Connection Adapter

Provides async-compatible connection context managers backed by the local
SQLite database at data/frxbot_brain.db. Replaces the legacy asyncpg
PostgreSQL connection pool with zero-latency local I/O.

All public function signatures are preserved so existing callers
(queries.py, add_to_whitelist.py, etc.) continue to work unchanged.
"""

import os
import sqlite3
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any, Optional

logger = logging.getLogger(__name__)

# Resolve the path to our local SQLite database
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, "data", "frxbot_brain.db")


class _SQLiteConnectionWrapper:
    """
    Lightweight async-style wrapper around a sqlite3 connection.
    Exposes fetchval / fetchrow / execute methods matching the asyncpg
    interface used by queries.py, so existing callers require zero changes.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.row_factory = sqlite3.Row

    async def execute(self, query: str, *args: Any) -> None:
        """Executes a query (INSERT/UPDATE/DELETE) with positional params."""
        sql = _convert_pg_placeholders(query)
        self._conn.execute(sql, args)
        self._conn.commit()

    async def fetchval(self, query: str, *args: Any) -> Optional[Any]:
        """Executes a query and returns the first column of the first row."""
        sql = _convert_pg_placeholders(query)
        cursor = self._conn.execute(sql, args)
        row = cursor.fetchone()
        if row:
            return row[0]
        return None

    async def fetchrow(self, query: str, *args: Any) -> Optional[sqlite3.Row]:
        """Executes a query and returns the first row as a dict-like Row."""
        sql = _convert_pg_placeholders(query)
        cursor = self._conn.execute(sql, args)
        return cursor.fetchone()


def _convert_pg_placeholders(query: str) -> str:
    """
    Converts PostgreSQL-style positional placeholders ($1, $2, ...) to
    SQLite-style question mark placeholders (?).
    Also strips unsupported PostgreSQL clauses like RETURNING.
    """
    import re
    # Remove RETURNING clauses (SQLite uses lastrowid instead)
    query = re.sub(r'\s+RETURNING\s+\w+\s*;?\s*$', ';', query, flags=re.IGNORECASE)
    # Replace $N placeholders with ?
    query = re.sub(r'\$\d+', '?', query)
    return query


# ──────────────────────────────────────────────────────────────────────
# Public API (preserves legacy function signatures)
# ──────────────────────────────────────────────────────────────────────

async def init_db_pool() -> bool:
    """
    Initializes the local SQLite database and ensures core tables exist.
    Returns True immediately — no network I/O, no retries needed.
    Replaces the legacy asyncpg pool initialization.
    """
    try:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(_DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()

        # Ensure the whitelist_users table exists locally
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whitelist_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                telegram_id INTEGER,
                username TEXT,
                full_name TEXT,
                is_active BOOLEAN DEFAULT 1
            );
        """)

        # Ensure the signals_log table exists locally
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                mode TEXT,
                timeframe TEXT,
                direction TEXT,
                entry_price REAL,
                sl_price REAL,
                tp1_price REAL,
                tp2_price REAL,
                lot_size REAL,
                atr_value REAL,
                signal_source TEXT,
                ai_confidence REAL,
                ai_reasoning TEXT,
                outcome TEXT DEFAULT 'OPEN',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()
        conn.close()
        logger.info(f"SQLite connection adapter initialized at {_DB_PATH}")
        return True
    except Exception as e:
        logger.error(f"SQLite init error: {e}", exc_info=True)
        return False


async def close_db_pool() -> None:
    """
    No-op for SQLite — connections are opened/closed per operation.
    Preserves the legacy function signature for callers like add_to_whitelist.py.
    """
    logger.info("SQLite adapter: close_db_pool called (no-op for local SQLite).")


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[_SQLiteConnectionWrapper, None]:
    """
    Async context manager that yields a wrapped SQLite connection.
    Drop-in replacement for the legacy asyncpg pool acquire/release pattern.

    Usage:
        async with get_db_connection() as conn:
            await conn.execute("INSERT INTO ...", val1, val2)
            row = await conn.fetchrow("SELECT ... WHERE user_id = ?", uid)
    """
    conn = None
    try:
        conn = sqlite3.connect(_DB_PATH)
        wrapper = _SQLiteConnectionWrapper(conn)
        yield wrapper
    except Exception as e:
        logger.error(f"SQLite connection error: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()
