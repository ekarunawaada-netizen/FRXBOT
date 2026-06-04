import os
import asyncio
import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager
import asyncpg

from core.config import settings

logger = logging.getLogger(__name__)

# Global variable to store connection pool
_db_pool: asyncpg.Pool | None = None

# Connection retry settings
_MAX_INIT_RETRIES = 3
_INIT_RETRY_DELAY_S = 5  # seconds between retries


async def init_db_pool() -> asyncpg.Pool | None:
    """
    Initializes the asyncpg connection pool with retry logic.
    
    Reads parameters from Pydantic settings (loaded from .env):
    - DATABASE_URL: PostgreSQL connection string
    - DB_POOL_MIN: Minimum number of connections (default 2)
    - DB_POOL_MAX: Maximum number of connections (default 10)
    
    Returns the pool on success, or None if all retries fail (non-blocking).
    """
    global _db_pool
    if _db_pool is not None:
        logger.info("Database pool already initialized.")
        return _db_pool

    database_url = settings.database_url
    if not database_url or database_url == "postgresql://postgres:postgres@localhost:5432/forex_bot":
        logger.warning(f"DATABASE_URL not set or using default fallback: {database_url}")

    min_size = settings.db_pool_min
    max_size = settings.db_pool_max

    for attempt in range(1, _MAX_INIT_RETRIES + 1):
        try:
            _db_pool = await asyncio.wait_for(
                asyncpg.create_pool(
                    dsn=database_url,
                    min_size=min_size,
                    max_size=max_size,
                    timeout=15.0,        # per-connection acquire timeout
                    command_timeout=30.0, # per-query timeout
                ),
                timeout=20.0  # overall timeout for the entire pool init (DNS + TCP + handshake)
            )
            logger.info(f"Database connection pool initialized (min_size={min_size}, max_size={max_size}).")
            return _db_pool

        except asyncio.TimeoutError:
            logger.error(
                f"Database pool init timed out (attempt {attempt}/{_MAX_INIT_RETRIES}). "
                f"DNS or network may be unreachable."
            )
        except OSError as e:
            # Catches getaddrinfo failed, Connection refused, Network unreachable, etc.
            logger.error(
                f"Database pool init OS/network error (attempt {attempt}/{_MAX_INIT_RETRIES}): {e}"
            )
        except Exception as e:
            logger.error(
                f"Database pool init failed (attempt {attempt}/{_MAX_INIT_RETRIES}): {e}"
            )

        if attempt < _MAX_INIT_RETRIES:
            logger.info(f"Retrying database connection in {_INIT_RETRY_DELAY_S}s...")
            await asyncio.sleep(_INIT_RETRY_DELAY_S)

    logger.error(
        f"All {_MAX_INIT_RETRIES} database connection attempts failed. "
        f"Bot will continue without database — signal logging and whitelist checks will be unavailable."
    )
    _db_pool = None
    return None


async def close_db_pool() -> None:
    """Closes the asyncpg connection pool gracefully."""
    global _db_pool
    if _db_pool is not None:
        try:
            await _db_pool.close()
            logger.info("Database connection pool closed successfully.")
        except Exception as e:
            logger.error(f"Error closing database pool: {str(e)}")
        finally:
            _db_pool = None


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Asynchronous context manager to borrow a connection from the pool.
    
    Yields:
        An active asyncpg.Connection object.
    
    Raises:
        RuntimeError: If connection pool is not available after initialization attempt.
    """
    global _db_pool
    if _db_pool is None:
        logger.warning("Connection pool not initialized. Attempting initialization.")
        await init_db_pool()
        if _db_pool is None:
            raise RuntimeError(
                "Database connection pool is not available. "
                "Check DATABASE_URL and network connectivity."
            )

    try:
        conn = await asyncio.wait_for(_db_pool.acquire(), timeout=10.0)
    except asyncio.TimeoutError:
        raise RuntimeError("Timed out waiting to acquire a database connection from the pool.")
    
    try:
        yield conn
    finally:
        await _db_pool.release(conn)
