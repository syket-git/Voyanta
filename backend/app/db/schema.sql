-- Applied on every boot. Every statement must stay idempotent.
--
-- LangGraph's checkpointer owns the message history and creates its own tables. These
-- are the tables it has no concept of: who a thread belongs to, and what it is called.

CREATE TABLE IF NOT EXISTS users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text NOT NULL,
    password_hash text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Case-insensitive uniqueness, without depending on the citext extension.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_key ON users (lower(email));

-- token_hash, never the token: a dump of this table must not yield usable sessions.
CREATE TABLE IF NOT EXISTS sessions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text NOT NULL UNIQUE,
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions (user_id);

-- id doubles as the LangGraph thread_id, so one identifier spans both systems and this
-- table becomes the index the checkpoint tables lack.
CREATE TABLE IF NOT EXISTS threads (
    id         uuid PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title      text NOT NULL DEFAULT 'New trip',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS threads_user_updated_idx ON threads (user_id, updated_at DESC);

-- Billing. `plan` is this app's own record of what a user is entitled to, written by the
-- Stripe webhook. The request path reads it from here and never calls Stripe: an API
-- round trip on every turn would put Stripe's availability in front of the chat endpoint.
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id     text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan                   text NOT NULL DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status    text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_period_end     timestamptz;

-- The webhook looks users up by customer id, so two rows must never claim the same one.
CREATE UNIQUE INDEX IF NOT EXISTS users_stripe_customer_key
    ON users (stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

-- One row per user per calendar month, created on first use. Quota resets are therefore
-- a consequence of the period key changing, not of a scheduled job that could fail to run.
CREATE TABLE IF NOT EXISTS usage_counters (
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    period     text NOT NULL,
    turns      integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, period)
);

-- Stripe redelivers webhooks until it gets a 2xx, and delivers at-least-once regardless.
-- A row here makes the second delivery of an event a no-op.
CREATE TABLE IF NOT EXISTS stripe_events (
    id           text PRIMARY KEY,
    type         text NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now()
);
