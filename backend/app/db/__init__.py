"""Schema management.

There is no ORM or migration tool here: the app talks raw psycopg, and the schema is a
single idempotent file applied at startup, alongside the checkpointer's own `setup()`.
Reach for Alembic when a column needs to change shape rather than merely appear.
"""

import logging
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


async def apply_schema(pool: AsyncConnectionPool) -> None:
    # prepare=False is required: the pool sets prepare_threshold=0 for the checkpointer,
    # and a prepared statement cannot carry more than one command.
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(SCHEMA_PATH.read_text(), prepare=False)

    logger.info("schema applied")
