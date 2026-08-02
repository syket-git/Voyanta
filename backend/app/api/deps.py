"""Request dependencies.

`require_user` is the single gate every non-public route goes through. Authorisation
lives here rather than in the frontend: the API is reachable on its own, so a check that
only runs in Next.js protects nothing.
"""

from fastapi import Depends, HTTPException, Request, status

from app.auth.sessions import AuthenticatedUser, resolve_session
from app.config import settings


async def current_user(request: Request) -> AuthenticatedUser | None:
    token = request.cookies.get(settings.session_cookie_name)
    return await resolve_session(request.app.state.pool, token)


async def require_user(
    user: AuthenticatedUser | None = Depends(current_user),
) -> AuthenticatedUser:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
        )

    return user
