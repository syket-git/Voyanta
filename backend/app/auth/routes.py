"""Signup, login, logout, and who-am-I."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from app.api.deps import require_user
from app.api.limiter import limiter
from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import AuthenticatedUser, issue_session, revoke_session
from app.config import settings
from app.schemas import LoginRequest, SignupRequest, UserOut

logger = logging.getLogger(__name__)
router = APIRouter()

AUTH_RATE_LIMIT = "10/minute"


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "dev",
        path="/",
        # No domain on purpose: it must default to the host the browser actually saw,
        # which is the Next.js origin, not this API's.
    )


@router.post("/auth/signup", response_model=UserOut, status_code=201)
@limiter.limit(AUTH_RATE_LIMIT)
async def signup(req: SignupRequest, request: Request, response: Response) -> UserOut:
    """Create an account and sign in."""
    pool = request.app.state.pool

    try:
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            RETURNING id::text AS id, email
            """,
                (req.email, hash_password(req.password)),
            )
            user = await cur.fetchone()
    except UniqueViolation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That email is already registered. Sign in instead.",
        ) from None

    token, _ = await issue_session(pool, user["id"])
    _set_session_cookie(response, token)

    logger.info("account created", extra={"user_id": user["id"]})

    return UserOut(**user)


@router.post("/auth/login", response_model=UserOut)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(req: LoginRequest, request: Request, response: Response) -> UserOut:
    """Exchange credentials for a session cookie."""
    pool = request.app.state.pool

    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id::text AS id, email, password_hash
            FROM users
            WHERE lower(email) = lower(%s)
            """,
            (req.email,),
        )
        user = await cur.fetchone()

    # verify_password falls back to a dummy hash when the row is missing, so an unknown
    # email costs the same time as a wrong password.
    if not verify_password(user["password_hash"] if user else None, req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That email and password do not match.",
        )

    token, _ = await issue_session(pool, user["id"])
    _set_session_cookie(response, token)

    logger.info("signed in", extra={"user_id": user["id"]})

    return UserOut(id=user["id"], email=user["email"])


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    """Revoke the current session. Safe to call when already signed out."""
    token = request.cookies.get(settings.session_cookie_name)

    await revoke_session(request.app.state.pool, token)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/auth/me", response_model=UserOut)
async def me(user: AuthenticatedUser = Depends(require_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email)
