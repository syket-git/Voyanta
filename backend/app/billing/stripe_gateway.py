"""Everything that talks to Stripe.

Two rules shape this module.

Access is granted by webhook, never by the browser coming back from Checkout. The success
URL is a redirect the user controls: it can be opened directly, replayed, or never
visited at all after a perfectly good payment. Only the webhook is Stripe telling the
server what happened.

And every webhook re-fetches the subscription instead of trusting the payload it arrived
with. Stripe does not promise delivery order, so an older `subscription.updated` can land
after a newer one and write back state that is no longer true. Re-fetching makes order
irrelevant — each event is just a prompt to go and look.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import stripe
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.auth.sessions import AuthenticatedUser
from app.billing.quota import ENTITLED_STATUSES, FREE, PRO
from app.config import settings

logger = logging.getLogger(__name__)

# Events worth acting on. Everything else Stripe sends is acknowledged and dropped —
# returning a non-2xx for an event we do not handle only earns a retry loop.
SUBSCRIPTION_EVENTS = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.paused",
        "customer.subscription.resumed",
    }
)

_client: stripe.StripeClient | None = None


def field(obj: Any, key: str, default: Any = None) -> Any:
    """Read one field from a Stripe object.

    `StripeObject` is dict-like for subscripting but routes attribute access through
    `__getattr__`, so calling `.get()` on one raises `AttributeError: get` rather than
    returning a default. Subscripting works on both it and a plain dict.
    """
    try:
        value = obj[key]
    except (KeyError, TypeError, AttributeError):
        return default

    return default if value is None else value


def client() -> stripe.StripeClient:
    """The Stripe client, built once on first use.

    Lazily, because the API must still boot with billing unconfigured — a missing key
    should fail the two billing routes, not the whole process.
    """
    global _client

    if _client is None:
        if not settings.stripe_secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY is not set.")

        # An async-only HTTP client: a sync call would block the event loop, and this
        # raises on one rather than quietly stalling every other request.
        _client = stripe.StripeClient(
            settings.stripe_secret_key,
            http_client=stripe.HTTPXClient(),
        )

    return _client


def _period_end(subscription: Any) -> datetime | None:
    """When the paid-for period runs out.

    The field moved onto the subscription's items — a subscription can hold items on
    different cadences, so there is no single period at the top level any more. The
    top-level read is the fallback for accounts still pinned to an older API version.
    """
    epoch = field(subscription, "current_period_end")

    if epoch is None:
        items = field(field(subscription, "items", {}), "data", [])
        epoch = field(items[0], "current_period_end") if items else None

    return datetime.fromtimestamp(epoch, UTC) if epoch else None


async def ensure_customer(
    pool: AsyncConnectionPool, user: AuthenticatedUser
) -> str:
    """The user's Stripe customer id, creating the customer the first time.

    `metadata.user_id` is the reverse link: it is what lets a Stripe dashboard row or an
    event about an unrecognised customer be traced back to an account here.
    """
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT stripe_customer_id FROM users WHERE id = %s", (user.id,)
        )
        row = await cur.fetchone()

    if row and row["stripe_customer_id"]:
        return row["stripe_customer_id"]

    customer = await client().v1.customers.create_async(
        {"email": user.email, "metadata": {"user_id": user.id}}
    )

    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Conditional, so two simultaneous first-checkouts cannot overwrite each other.
        # The loser's customer is left unused in Stripe rather than attached to the user:
        # a stray empty customer costs nothing, a swapped one loses a subscription.
        await cur.execute(
            """
            UPDATE users SET stripe_customer_id = %s
             WHERE id = %s AND stripe_customer_id IS NULL
            RETURNING stripe_customer_id
            """,
            (customer.id, user.id),
        )
        claimed = await cur.fetchone()

        if claimed:
            return claimed["stripe_customer_id"]

        await cur.execute(
            "SELECT stripe_customer_id FROM users WHERE id = %s", (user.id,)
        )
        existing = await cur.fetchone()

    logger.info("discarding duplicate stripe customer", extra={"user_id": user.id})

    return existing["stripe_customer_id"]


async def create_checkout_session(
    pool: AsyncConnectionPool, user: AuthenticatedUser
) -> str:
    """Start a subscription and return the URL to send the browser to.

    Card details are entered on Stripe's page and never touch this server, which is what
    keeps the PCI obligation down to a redirect.
    """
    customer_id = await ensure_customer(pool, user)

    session = await client().v1.checkout.sessions.create_async(
        {
            "mode": "subscription",
            "customer": customer_id,
            "line_items": [{"price": settings.stripe_price_id, "quantity": 1}],
            "success_url": f"{settings.billing_return_url}?checkout=success",
            "cancel_url": f"{settings.billing_return_url}?checkout=cancelled",
            "allow_promotion_codes": True,
            "client_reference_id": user.id,
            "subscription_data": {"metadata": {"user_id": user.id}},
        }
    )

    logger.info(
        "checkout session created",
        extra={"user_id": user.id, "session_id": session.id},
    )

    return session.url


async def create_portal_session(
    pool: AsyncConnectionPool, user: AuthenticatedUser
) -> str:
    """Stripe's own page for cancelling, swapping cards and downloading invoices.

    Hosted rather than rebuilt here: those screens are where the dunning emails, tax
    receipts and proration rules already live.
    """
    customer_id = await ensure_customer(pool, user)

    session = await client().v1.billing_portal.sessions.create_async(
        {"customer": customer_id, "return_url": settings.billing_return_url}
    )

    return session.url


async def _user_id_for(
    pool: AsyncConnectionPool, customer_id: str | None, fallback: str | None
) -> str | None:
    if customer_id:
        async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id::text AS id FROM users WHERE stripe_customer_id = %s",
                (customer_id,),
            )
            row = await cur.fetchone()

        if row:
            return row["id"]

    # Reached when the customer was created outside this app, or when checkout completed
    # before the customer id was written back. The metadata carried on the object is the
    # only remaining link.
    return fallback


async def _apply_subscription(
    pool: AsyncConnectionPool, subscription: Any, fallback_user_id: str | None
) -> None:
    customer_id = field(subscription, "customer")
    if not isinstance(customer_id, str):
        customer_id = getattr(customer_id, "id", None)

    user_id = await _user_id_for(
        pool,
        customer_id,
        fallback_user_id or field(field(subscription, "metadata", {}), "user_id"),
    )

    if user_id is None:
        logger.warning(
            "subscription for unknown customer", extra={"customer_id": customer_id}
        )
        return

    status = field(subscription, "status")
    entitled = status in ENTITLED_STATUSES
    plan = PRO.name if entitled else FREE.name

    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE users
               SET plan                   = %s,
                   subscription_status    = %s,
                   stripe_subscription_id = %s,
                   current_period_end     = %s,
                   stripe_customer_id     = COALESCE(stripe_customer_id, %s)
             WHERE id = %s
            """,
            (
                plan,
                status,
                field(subscription, "id"),
                _period_end(subscription),
                customer_id,
                user_id,
            ),
        )

    logger.info(
        "subscription applied",
        extra={"user_id": user_id, "plan": plan, "status": status},
    )


async def _claim_event(pool: AsyncConnectionPool, event: Any) -> bool:
    """Record the event id, and report whether this delivery is the first one."""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO stripe_events (id, type) VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """,
            (field(event, "id"), field(event, "type")),
        )
        return await cur.fetchone() is not None


def parse_event(payload: bytes, signature: str | None) -> Any:
    """Verify the signature and decode the event.

    Without this the endpoint is an unauthenticated way to grant anyone a subscription:
    the URL is public, and the body is otherwise just JSON claiming a payment happened.
    """
    if not signature:
        raise stripe.SignatureVerificationError("Missing Stripe-Signature header.", None)

    return client().construct_event(
        payload, signature, settings.stripe_webhook_secret or ""
    )


async def handle_event(pool: AsyncConnectionPool, event: Any) -> None:
    event_type = field(event, "type")

    if event_type not in SUBSCRIPTION_EVENTS:
        logger.debug("ignoring stripe event", extra={"event_type": event_type})
        return

    if not await _claim_event(pool, event):
        logger.info("stripe event already processed", extra={"event_id": field(event, "id")})
        return

    obj = field(field(event, "data", {}), "object", {})

    if event_type == "checkout.session.completed":
        subscription_id = field(obj, "subscription")
        fallback_user_id = field(obj, "client_reference_id")

        if not subscription_id:
            return
    else:
        subscription_id = field(obj, "id")
        fallback_user_id = field(field(obj, "metadata", {}), "user_id")

    if not isinstance(subscription_id, str):
        subscription_id = getattr(subscription_id, "id", None)

    subscription = await client().v1.subscriptions.retrieve_async(subscription_id)

    await _apply_subscription(pool, subscription, fallback_user_id)
