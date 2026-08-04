"""Usage, checkout, the customer portal, and the Stripe webhook."""

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import require_user
from app.api.limiter import limiter
from app.auth.sessions import AuthenticatedUser
from app.billing import read_account
from app.billing import stripe_gateway as gateway
from app.config import settings
from app.schemas import BillingRedirect, BillingStatus

logger = logging.getLogger(__name__)
router = APIRouter()

BILLING_RATE_LIMIT = "20/minute"


def _require_stripe() -> None:
    if not settings.billing_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured on this deployment.",
        )


@router.get("/billing/status", response_model=BillingStatus)
async def billing_status(
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
) -> BillingStatus:
    """What the caller is on and how much of it is left."""
    account = await read_account(request.app.state.pool, user.id)

    if account is None:
        raise HTTPException(status_code=404, detail="No account found.")

    return BillingStatus(
        plan=account.plan.name,
        plan_label=account.plan.label,
        turns_used=account.turns_used,
        turns_limit=account.plan.turns_per_month,
        turns_remaining=account.turns_remaining,
        period_end=account.period_end,
        price_label=settings.pro_price_label,
        subscription_status=account.subscription_status,
        billing_enabled=settings.billing_enabled,
        manageable=bool(account.stripe_customer_id),
    )


@router.post("/billing/checkout", response_model=BillingRedirect)
@limiter.limit(BILLING_RATE_LIMIT)
async def checkout(
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
) -> BillingRedirect:
    """Return the Stripe Checkout URL to send the browser to."""
    _require_stripe()

    return BillingRedirect(
        url=await gateway.create_checkout_session(request.app.state.pool, user)
    )


@router.post("/billing/portal", response_model=BillingRedirect)
@limiter.limit(BILLING_RATE_LIMIT)
async def portal(
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
) -> BillingRedirect:
    """Return the Stripe customer portal URL — cancel, change card, download invoices."""
    _require_stripe()

    return BillingRedirect(
        url=await gateway.create_portal_session(request.app.state.pool, user)
    )


@router.post("/billing/webhook", include_in_schema=False)
async def webhook(request: Request) -> Response:
    """Stripe's notification endpoint. Public by design, trusted only via its signature.

    Point Stripe straight at this URL rather than at the Next.js proxy: the signature is
    computed over the exact bytes of the body, and a proxy that re-encodes JSON on the
    way through invalidates it.
    """
    _require_stripe()

    payload = await request.body()

    try:
        event = gateway.parse_event(payload, request.headers.get("stripe-signature"))
    except stripe.SignatureVerificationError:
        logger.warning("rejected stripe webhook with a bad signature")
        raise HTTPException(status_code=400, detail="Invalid signature.") from None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload.") from None

    # A raised exception here becomes a 500, which Stripe answers by redelivering. That is
    # the behaviour we want for a transient database failure, so nothing is caught.
    await gateway.handle_event(request.app.state.pool, event)

    return Response(status_code=200)
