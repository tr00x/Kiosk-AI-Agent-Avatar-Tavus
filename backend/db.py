"""db.py — Async MySQL connection module for Open Dental database.

Features:
- Connection pooling via aiomysql (async-compatible with FastAPI)
- Non-blocking startup: backend starts instantly, DB connects in background
- Auto-reconnect: if DB drops, pool is recreated on next query
- Background retry loop keeps trying until DB is available
"""

import asyncio
import logging
from typing import Optional

import aiomysql

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------
pool: Optional[aiomysql.Pool] = None
_pool_lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None
_bg_task: Optional[asyncio.Task] = None


def _get_lock() -> asyncio.Lock:
    """Lazy-init lock (must be created inside running event loop)."""
    global _pool_lock
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    return _pool_lock


async def _create_pool() -> Optional[aiomysql.Pool]:
    """Try to create MySQL pool once. Returns pool or None."""
    try:
        p = await aiomysql.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            db=settings.db_name,
            minsize=1,
            maxsize=5,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=3,
        )
        logger.info("MySQL pool connected (%s:%s/%s)", settings.db_host, settings.db_port, settings.db_name)
        return p
    except Exception as exc:
        logger.warning("MySQL connect failed: %s", exc)
        return None


async def _kill_pool() -> None:
    """Safely close a dead pool."""
    global pool
    if pool is not None:
        try:
            pool.close()
            await pool.wait_closed()
        except Exception:
            pass
        pool = None


# ---------------------------------------------------------------------------
# Background retry loop
# ---------------------------------------------------------------------------

async def _bg_connect_loop() -> None:
    """Keep trying to connect to MySQL in background until success."""
    global pool
    delays = [1, 2, 5, 10, 15, 30]  # escalating retry
    attempt = 0
    while True:
        if pool is not None:
            return
        pool = await _create_pool()
        if pool is not None:
            return
        delay = delays[min(attempt, len(delays) - 1)]
        logger.info("DB retry in %ds (attempt %d)...", delay, attempt + 1)
        await asyncio.sleep(delay)
        attempt += 1


async def init_pool() -> None:
    """Schedule DB connect in background — backend starts instantly."""
    global _bg_task
    _bg_task = asyncio.create_task(_bg_connect_loop())


async def ensure_pool() -> None:
    """Ensure pool is alive before each query. Reconnects if needed."""
    global pool
    async with _get_lock():
        # Pool exists — test if it's alive
        if pool is not None:
            try:
                async with pool.acquire() as conn:
                    await conn.ping()
                return  # pool is healthy
            except Exception:
                logger.warning("MySQL pool dead, reconnecting...")
                await _kill_pool()

        # Pool is None — try to create
        pool = await _create_pool()
        if pool is None:
            raise RuntimeError("Database not available")


async def close_pool() -> None:
    """Close the connection pool. Called during FastAPI shutdown."""
    global pool, _bg_task
    if _bg_task and not _bg_task.done():
        _bg_task.cancel()
        _bg_task = None
    if pool is not None:
        pool.close()
        await pool.wait_closed()
        pool = None
        logger.info("MySQL connection pool closed")


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

async def execute_query(query: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT query and return rows as list of dicts."""
    await ensure_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, params)
            rows = await cur.fetchall()
            return list(rows)


async def execute_insert(query: str, params: tuple = ()) -> int:
    """Execute an INSERT/UPDATE query and return the last row ID."""
    await ensure_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            await conn.commit()
            return cur.lastrowid


async def execute_update(query: str, params: tuple = ()) -> int:
    """Execute an UPDATE/DELETE query and return affected rows."""
    await ensure_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            await conn.commit()
            return cur.rowcount


async def execute_ddl(query: str) -> None:
    """Execute a DDL statement (CREATE TABLE, etc.)."""
    await ensure_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query)
            await conn.commit()
