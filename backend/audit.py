"""HIPAA-compliant audit logging for the dental kiosk.

Every tool call and sensitive action is logged to the kiosk_audit_log table.
Logging is fire-and-forget — it NEVER blocks the tool webhook response.
"""

import asyncio
import logging
from typing import Optional

from db import execute_ddl, execute_insert

logger = logging.getLogger(__name__)

_TABLE_CREATED = False


async def _ensure_table() -> None:
    """Create the audit log table if it doesn't exist."""
    global _TABLE_CREATED
    if _TABLE_CREATED:
        return
    try:
        await execute_ddl("""
            CREATE TABLE IF NOT EXISTS kiosk_audit_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                conversation_id VARCHAR(255),
                tool_name VARCHAR(100),
                patient_id INT NULL,
                action VARCHAR(255),
                result_summary TEXT
            )
        """)
        _TABLE_CREATED = True
    except Exception as e:
        logger.warning("Failed to create audit table: %s", e)


async def _write_log(
    conversation_id: str,
    tool_name: str,
    patient_id: Optional[int],
    action: str,
    result_summary: str,
) -> None:
    """Internal: actually write the audit log entry."""
    await _ensure_table()
    try:
        await execute_insert(
            """
            INSERT INTO kiosk_audit_log
                (conversation_id, tool_name, patient_id, action, result_summary)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (conversation_id, tool_name, patient_id, action, result_summary),
        )
    except Exception as e:
        logger.warning("Audit log write failed: %s", e)


async def log_tool_call(
    conversation_id: str,
    tool_name: str,
    patient_id: Optional[int],
    action: str,
    result_summary: str = "",
) -> None:
    """Write an audit log entry — fire-and-forget, never blocks caller."""
    asyncio.create_task(
        _write_log(conversation_id, tool_name, patient_id, action, result_summary)
    )
