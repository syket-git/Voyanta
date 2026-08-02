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
