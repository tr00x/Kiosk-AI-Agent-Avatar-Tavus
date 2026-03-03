"""db.py — Async MySQL connection module for Open Dental database.

Features:
- Connection pooling via aiomysql (async-compatible with FastAPI)
- Retry with exponential backoff on connection failures
- Pool lifecycle managed by FastAPI lifespan events
"""

import asyncio
import logging
from typing import Optional

import aiomysql

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool (initialized on FastAPI startup)
# ---------------------------------------------------------------------------
pool: Optional[aiomysql.Pool] = None

_MAX_RETRIES = 3
_RETRY_DELAYS = [1, 2, 4]  # seconds between retries


async def init_pool() -> None:
    """Create the async MySQL connection pool.

    Called once during FastAPI startup.
    """
    global pool
    last_error: Optional[Exception] = None

    for attempt in range(_MAX_RETRIES):
        try:
            pool = await aiomysql.create_pool(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                db=settings.db_name,
                minsize=1,
                maxsize=5,
                charset="utf8mb4",
                autocommit=True,
                connect_timeout=10,
            )
            logger.info("MySQL connection pool created (maxsize=5)")
            return
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "DB pool creation attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise RuntimeError(
                    f"Failed to create MySQL pool after {_MAX_RETRIES} attempts: {last_error}"
                ) from last_error


async def close_pool() -> None:
    """Close the connection pool. Called during FastAPI shutdown."""
    global pool
    if pool is not None:
        pool.close()
        await pool.wait_closed()
        pool = None
        logger.info("MySQL connection pool closed")


async def execute_query(query: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT query and return rows as list of dicts.

    Uses a connection from the pool with automatic retry on failure.
    """
    if pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")

    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(query, params)
                    rows = await cur.fetchall()
                    return list(rows)
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "DB query attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise RuntimeError(
                    f"Query failed after {_MAX_RETRIES} attempts: {last_error}"
                ) from last_error
    return []


async def execute_insert(query: str, params: tuple = ()) -> int:
    """Execute an INSERT/UPDATE query and return the last row ID (or affected rows).

    Uses a connection from the pool with automatic retry.
    """
    if pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")

    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, params)
                    await conn.commit()
                    return cur.lastrowid
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "DB insert attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise RuntimeError(
                    f"Insert failed after {_MAX_RETRIES} attempts: {last_error}"
                ) from last_error
    return 0


async def execute_update(query: str, params: tuple = ()) -> int:
    """Execute an UPDATE/DELETE query and return the number of affected rows.

    Uses a connection from the pool with automatic retry.
    """
    if pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")

    last_error: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, params)
                    await conn.commit()
                    return cur.rowcount
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(
                    "DB update attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise RuntimeError(
                    f"Update failed after {_MAX_RETRIES} attempts: {last_error}"
                ) from last_error
    return 0


async def execute_ddl(query: str) -> None:
    """Execute a DDL statement (CREATE TABLE, etc.)."""
    if pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query)
            await conn.commit()
