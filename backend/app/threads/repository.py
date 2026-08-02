"""Thread queries.

Every statement here filters on `user_id`. Ownership is enforced in the WHERE clause
rather than by a separate check, so there is no path that reads a thread without also
proving who it belongs to.
"""

import re
import uuid

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.schemas import ThreadSummary

TITLE_MAX_LENGTH = 60
DEFAULT_TITLE = "New trip"


def title_from_message(message: str) -> str:
    """Derive a sidebar title from the first thing the traveller said."""
    cleaned = re.sub(r"\s+", " ", message).strip()

    if not cleaned:
        return DEFAULT_TITLE

    if len(cleaned) <= TITLE_MAX_LENGTH:
        return cleaned

    # Prefer cutting at a word boundary, but only if that keeps most of the width.
    clipped = cleaned[:TITLE_MAX_LENGTH]
    spaced = clipped.rsplit(" ", 1)[0]

    return f"{spaced if len(spaced) > TITLE_MAX_LENGTH * 0.6 else clipped}…"


async def list_threads(
    pool: AsyncConnectionPool, user_id: str, limit: int = 200
) -> list[ThreadSummary]:
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id::text AS id, title, created_at, updated_at
            FROM threads
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        rows = await cur.fetchall()

    return [ThreadSummary(**row) for row in rows]


async def create_thread(
    pool: AsyncConnectionPool,
    user_id: str,
    title: str = DEFAULT_TITLE,
    thread_id: str | None = None,
) -> ThreadSummary:
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO threads (id, user_id, title)
            VALUES (%s, %s, %s)
            RETURNING id::text AS id, title, created_at, updated_at
            """,
            (thread_id or str(uuid.uuid4()), user_id, title),
        )
        row = await cur.fetchone()

    return ThreadSummary(**row)


async def owns_thread(pool: AsyncConnectionPool, user_id: str, thread_id: str) -> bool:
    # A malformed id is simply not owned; letting it reach Postgres as a uuid comparison
    # would raise instead of returning False.
    try:
        uuid.UUID(thread_id)
    except ValueError:
        return False

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM threads WHERE id = %s AND user_id = %s",
            (thread_id, user_id),
        )
        return await cur.fetchone() is not None


async def touch_thread(pool: AsyncConnectionPool, user_id: str, thread_id: str) -> None:
    """Move a thread to the top of the sidebar after a turn."""
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE threads SET updated_at = now() WHERE id = %s AND user_id = %s",
            (thread_id, user_id),
        )


async def rename_thread(
    pool: AsyncConnectionPool, user_id: str, thread_id: str, title: str
) -> ThreadSummary | None:
    if not await owns_thread(pool, user_id, thread_id):
        return None

    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE threads SET title = %s
            WHERE id = %s AND user_id = %s
            RETURNING id::text AS id, title, created_at, updated_at
            """,
            (title, thread_id, user_id),
        )
        row = await cur.fetchone()

    return ThreadSummary(**row) if row else None


async def delete_thread(pool: AsyncConnectionPool, user_id: str, thread_id: str) -> bool:
    if not await owns_thread(pool, user_id, thread_id):
        return False

    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM threads WHERE id = %s AND user_id = %s", (thread_id, user_id)
        )

    return True
