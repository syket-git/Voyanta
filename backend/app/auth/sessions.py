"""Opaque session tokens, validated against the database.

The token is random and carries no claims, so there is nothing to sign and no secret to
rotate. Only its SHA-256 is stored: reading the sessions table gives an attacker no way
to authenticate as anyone.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings

TOKEN_BYTES = 32


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_session(pool: AsyncConnectionPool, user_id: str) -> tuple[str, datetime]:
    """Create a session and return its plaintext token — the only time it exists."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(UTC) + timedelta(days=settings.session_ttl_days)

    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (_fingerprint(token), user_id, expires_at),
        )

    return token, expires_at


async def resolve_session(
    pool: AsyncConnectionPool, token: str | None
) -> AuthenticatedUser | None:
    if not token:
        return None

    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT users.id::text AS id, users.email
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = %s AND sessions.expires_at > now()
            """,
            (_fingerprint(token),),
        )
        row = await cur.fetchone()

    return AuthenticatedUser(id=row["id"], email=row["email"]) if row else None


async def revoke_session(pool: AsyncConnectionPool, token: str | None) -> None:
    if not token:
        return

    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM sessions WHERE token_hash = %s", (_fingerprint(token),)
        )


async def purge_expired(pool: AsyncConnectionPool) -> int:
    async with pool.connection() as conn:
        result = await conn.execute("DELETE FROM sessions WHERE expires_at <= now()")
        return result.rowcount
