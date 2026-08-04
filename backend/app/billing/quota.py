"""How many turns a user gets, and how many they have taken.

A turn — one message and the reply it produces — is the billable unit rather than tokens.
Tokens are the real cost, but nobody can look at "you have 140,000 left" and know whether
that is a lot. Token totals still go to LangSmith; they just do not gate anything.

The counter is keyed by calendar month, and its row is created by the first turn of that
month. Nothing resets the quota, because there is nothing to reset: a new month is a new
key, and the old row simply stops being read.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings


@dataclass(frozen=True)
class Plan:
    name: str
    label: str
    turns_per_month: int


FREE: Final = Plan("free", "Free", settings.free_turns_per_month)
PRO: Final = Plan("pro", "Pro", settings.pro_turns_per_month)

# `past_due` keeps its access on purpose. Stripe retries a failed charge over roughly two
# weeks, and most failures are an expired card rather than a decision to stop paying —
# locking the account on the first decline churns customers who were going to pay.
# `unpaid` is where those retries give up, and that does lose access.
ENTITLED_STATUSES: Final = frozenset({"active", "trialing", "past_due"})


@dataclass(frozen=True)
class Account:
    """A user's billing state, as this app records it — never fetched live from Stripe."""

    user_id: str
    plan: Plan
    turns_used: int
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    subscription_status: str | None
    current_period_end: datetime | None

    @property
    def turns_remaining(self) -> int:
        return max(self.plan.turns_per_month - self.turns_used, 0)

    @property
    def exhausted(self) -> bool:
        return self.turns_remaining == 0

    @property
    def period_end(self) -> datetime:
        """When the current allowance runs out: renewal on Pro, month end on Free."""
        if self.plan is PRO and self.current_period_end:
            return self.current_period_end
        return period_resets_at()


def current_period(now: datetime | None = None) -> str:
    """The counter key: `YYYY-MM` in UTC, so the reset is not a per-user local midnight."""
    return (now or datetime.now(UTC)).strftime("%Y-%m")


def period_resets_at(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    year, month = (moment.year + 1, 1) if moment.month == 12 else (moment.year, moment.month + 1)
    return datetime(year, month, 1, tzinfo=UTC)


def plan_for(name: str | None, status: str | None) -> Plan:
    """Both the recorded plan and the live subscription status have to agree.

    Either alone is enough to go wrong: a webhook that failed to land leaves `plan` stale,
    and a user who never subscribed has no status at all.
    """
    return PRO if name == PRO.name and status in ENTITLED_STATUSES else FREE


def _account_from_row(row: dict) -> Account:
    return Account(
        user_id=row["user_id"],
        plan=plan_for(row["plan"], row["subscription_status"]),
        turns_used=row["turns_used"],
        stripe_customer_id=row["stripe_customer_id"],
        stripe_subscription_id=row["stripe_subscription_id"],
        subscription_status=row["subscription_status"],
        current_period_end=row["current_period_end"],
    )


_ACCOUNT_QUERY = """
    SELECT users.id::text AS user_id,
           users.plan,
           users.subscription_status,
           users.stripe_customer_id,
           users.stripe_subscription_id,
           users.current_period_end,
           COALESCE(usage_counters.turns, 0) AS turns_used
    FROM users
    LEFT JOIN usage_counters
           ON usage_counters.user_id = users.id AND usage_counters.period = %s
    WHERE users.id = %s
"""


async def read_account(pool: AsyncConnectionPool, user_id: str) -> Account | None:
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_ACCOUNT_QUERY, (current_period(), user_id))
        row = await cur.fetchone()

    return _account_from_row(row) if row else None


_CAPPED_RESERVE = """
    INSERT INTO usage_counters (user_id, period, turns)
    VALUES (%s, %s, 1)
    ON CONFLICT (user_id, period) DO UPDATE
       SET turns = usage_counters.turns + 1, updated_at = now()
     WHERE usage_counters.turns < %s
    RETURNING turns
"""

_UNCAPPED_RESERVE = """
    INSERT INTO usage_counters (user_id, period, turns)
    VALUES (%s, %s, 1)
    ON CONFLICT (user_id, period) DO UPDATE
       SET turns = usage_counters.turns + 1, updated_at = now()
    RETURNING turns
"""


async def reserve_turn(
    pool: AsyncConnectionPool, user_id: str, *, enforce: bool = True
) -> Account | None:
    """Claim one turn up front, or return None when the allowance is spent.

    Claiming before the model runs rather than counting after it is what makes the limit
    hold: two turns sent at once would both read "19 used" and both be allowed. The
    increment is conditional inside a single statement, so the second one loses.

    With `enforce` off the turn is still counted but never refused. That is the shape a
    deployment without Stripe keys needs: a cap with no way to pay past it is not a
    business model, it is an outage.
    """
    account = await read_account(pool, user_id)

    if account is None or (enforce and account.plan.turns_per_month <= 0):
        return None

    query = _CAPPED_RESERVE if enforce else _UNCAPPED_RESERVE
    params: tuple = (user_id, current_period())

    if enforce:
        params += (account.plan.turns_per_month,)

    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, params)
        row = await cur.fetchone()

    # No row means the WHERE on the conflict path rejected the increment: already at the cap.
    if row is None:
        return None

    return Account(
        user_id=account.user_id,
        plan=account.plan,
        turns_used=row["turns"],
        stripe_customer_id=account.stripe_customer_id,
        stripe_subscription_id=account.stripe_subscription_id,
        subscription_status=account.subscription_status,
        current_period_end=account.current_period_end,
    )


async def release_turn(pool: AsyncConnectionPool, user_id: str) -> None:
    """Hand a reserved turn back after a run that produced nothing.

    Only for failures before or during generation. A turn the user cancelled halfway
    stays charged — the tokens were still bought.
    """
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE usage_counters
               SET turns = greatest(turns - 1, 0), updated_at = now()
             WHERE user_id = %s AND period = %s
            """,
            (user_id, current_period()),
        )
