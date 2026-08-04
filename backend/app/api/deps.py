"""Request dependencies.

`require_user` is the single gate every non-public route goes through. Authorisation
lives here rather than in the frontend: the API is reachable on its own, so a check that
only runs in Next.js protects nothing. `require_turn` is the same argument applied to
spending — the quota has to be enforced where the money is actually spent.
"""

from fastapi import Depends, HTTPException, Request, status

from app.auth.sessions import AuthenticatedUser, resolve_session
from app.billing import PRO, Account, read_account, reserve_turn
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


def _exhausted_message(account: Account | None) -> str:
    if account is None:
        return "That account no longer exists. Sign in again."

    if account.plan is PRO:
        return (
            f"You've used all {account.plan.turns_per_month} trips on Pro this month. "
            "That is the fair-use ceiling — reply to your receipt and we'll raise it."
        )

    return (
        f"You've used all {account.plan.turns_per_month} free trips this month. "
        f"Upgrade to Pro for {settings.pro_price_label} to keep planning, or come back "
        "when the allowance resets."
    )


async def require_turn(
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
) -> Account:
    """Reserve one turn, or refuse with 402.

    402 rather than 403: the request was understood and the caller is who they say they
    are — the only thing missing is payment, and the client needs to tell those apart to
    know whether to show a sign-in or an upgrade.
    """
    pool = request.app.state.pool
    account = await reserve_turn(pool, user.id, enforce=settings.billing_enabled)

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=_exhausted_message(await read_account(pool, user.id)),
        )

    return account
