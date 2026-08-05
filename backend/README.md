# Voyanta — Backend

The agent, and the HTTP API that exposes it.

This service runs a **LangGraph tour-planner agent** that turns a vague travel wish into a
day-by-day itinerary. It can look up live flight status and search the web, it remembers
each conversation in Postgres, and it reports every run to LangSmith. The frontend in
[`../frontend`](../frontend) is one client; the API is plain JSON and SSE, so anything can
call it.

**New here? Read the [mental model](#mental-model) first — it explains what happens when
someone sends a message. Then [Setup](#setup) and [Run](#run).**

> **LangGraph vs LangGraph Platform**
> This project uses the LangGraph *library* to build the agent, but **not** LangGraph
> *Platform* (the hosted product with `langgraph.json` and `langgraph dev`). The HTTP layer
> is hand-written FastAPI, so the JSON contract your frontend codes against is yours to
> own and version.

---

## Contents

1. [Mental model](#mental-model) — what happens on one message
2. [Setup](#setup) · [Environment variables](#environment-variables) · [Run](#run) · [Verify it works](#verify-it-works)
3. [The agent](#the-agent) — graph, tools, prompt guardrails
4. [API reference](#api-reference) — every endpoint
5. [Streaming contract](#streaming-contract) — the SSE frames, and how to consume them
6. [Data model](#data-model) · [Auth & security](#auth--security) · [Billing](#billing)
7. [Observability & debugging](#observability--debugging)
8. [Project layout](#project-layout) · [Troubleshooting](#troubleshooting) · [Known limits](#known-limits)

---

## Mental model

One message from a user is one **turn**. Here is everything that happens during it:

```
POST /api/chat/stream
        │
        ├─ 1. Session cookie → user            (require_user)
        ├─ 2. Reserve one turn from the quota  (require_turn → 402 if spent)
        ├─ 3. Resolve the thread               (mint a new one, or verify ownership)
        ├─ 4. Mint a run_id, open the SSE stream
        │
        └─ 5. Run the agent ────────────────────────────────┐
                                                            │
              ┌─────────────────────────────────────────┐   │
              │  model  ── needs data? ──▶  tools       │   │  every token and
              │    ▲                          │         │   │  every tool call is
              │    └──── observations ────────┘         │   │  streamed out as it
              │  no more tools ▶ final itinerary        │   │  happens
              └─────────────────────────────────────────┘   │
                      │                    │                │
              Postgres checkpoint      LangSmith trace ◀─────┘
              (so the thread            (so you can debug
               survives a restart)       the exact run)
```

Three things to hold on to:

- **A thread is the unit of memory.** Its id is passed back and forth; LangGraph stores the
  message history against it in Postgres.
- **A run is the unit of observability.** Every turn gets a `run_id`, returned to the
  client, so a 👍/👎 later can be attached to the exact trace.
- **A turn is the unit of billing.** Reserved before the model runs, refunded if the run
  produced nothing.

---

## Setup

**You need:** Python 3.14, [uv](https://docs.astral.sh/uv/), and a reachable Postgres
database (local, Docker, Neon, Supabase — anything with a connection string).

Every command below runs from this `backend/` directory.

```bash
cd backend
uv sync                  # creates .venv and installs everything from uv.lock
cp .env.example .env     # then fill in your keys
```

### Environment variables

Everything lives in `.env` next to this file. It is git-ignored. `.env.example` is the
annotated template — this table is what each key actually does.

**Required**

| Variable | What it's for |
|---|---|
| `OPENAI_API_KEY` | The model behind the agent. |
| `DATABASE_URL` | Postgres. Conversation history and all app tables live here. `postgresql://user:pass@host:5432/db` |

**Strongly recommended** — the app starts without these, but the agent is much less useful:

| Variable | What it's for |
|---|---|
| `TAVILY_API_KEY` | Web search. Without it, `web_search` returns a "key is missing" message *to the model*, which will tell the user. |
| `AVIATIONSTACK_API_KEY` | Live flight status. Same graceful-degradation behaviour. |
| `LANGSMITH_API_KEY` | Tracing. Without it, runs are untraced and the 👍/👎 endpoint quietly drops feedback. |

**Tuning** (all have sensible defaults)

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_MODEL` | `gpt-4.1` | Any chat model `langchain-openai` supports. |
| `OPENAI_TEMPERATURE` | `0.3` | Low on purpose — itineraries should be specific, not creative. |
| `LANGSMITH_PROJECT` | `voyanta-dev` | Use a separate project per environment. |
| `ENVIRONMENT` | `dev` | `dev` \| `staging` \| `prod`. Also controls the `secure` flag on the session cookie. |
| `CORS_ORIGINS` | `localhost:3000,127.0.0.1:3000` | Comma-separated. Only matters if a browser calls this API directly — the Next.js proxy makes requests same-origin, so normally it doesn't. |
| `CHAT_RATE_LIMIT` | `20/minute` | Per IP, on the chat endpoints. **Keep this on** — LLM calls cost real money and one runaway `useEffect` can drain a budget overnight. |
| `SESSION_TTL_DAYS` | `30` | How long a login lasts. |
| `RECURSION_LIMIT` | `25` | Max model↔tool hops in one turn. The stop on a looping agent. |
| `REQUEST_TIMEOUT` | `60` | Seconds. Without it, a hung OpenAI call holds a worker open forever. |
| `MAX_RETRIES` | `2` | Model-call retries. |
| `LOG_LEVEL` | `INFO` | |

**Billing** — optional; see [Billing](#billing). Leave blank and the app runs normally,
counting turns but never refusing them.

`STRIPE_SECRET_KEY` · `STRIPE_WEBHOOK_SECRET` · `STRIPE_PRICE_ID` · `BILLING_RETURN_URL` ·
`FREE_TURNS_PER_MONTH` (20) · `PRO_TURNS_PER_MONTH` (500) · `PRO_PRICE_LABEL`

---

## Run

**The API server** — what the frontend talks to:

```bash
uv run uvicorn app.api.main:app --reload --port 8000
```

Interactive docs (every endpoint, try-it-out included): <http://localhost:8000/docs>

**The terminal REPL** — the agent alone, **no database and no keys beyond OpenAI**. This is
the fastest way to iterate on the prompt or a tool:

```bash
uv run python scripts/cli_chat.py
```

It passes `InMemorySaver` instead of the Postgres checkpointer, so the conversation lives
only as long as the process. Same graph, same tools, same prompt.

**Docker** — from the repository root, brings up the API and the frontend together:

```bash
docker compose up --build
```

### What happens on boot

`main.py`'s lifespan does four things, in order, and logs each: opens the Postgres pool →
sets up LangGraph's checkpoint tables (idempotent) → applies
[`app/db/schema.sql`](app/db/schema.sql) (also idempotent) → builds the agent. If any of
them fails the server refuses to start, which is the correct behaviour: a chat API that
boots without a database would fail on the first message instead.

## Verify it works

```bash
# 1. Is it alive, and can it actually reach Postgres?
curl localhost:8000/health
# {"status":"ok","version":"0.1.0","environment":"dev","database":"ok","tracing":true}

# 2. Create an account (this stores the session cookie in cookies.txt)
curl -c cookies.txt -X POST localhost:8000/api/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"a-real-password"}'

# 3. Plan a trip
curl -b cookies.txt -X POST localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Plan a 3 day Bali trip from Dhaka for two people"}'
```

The response carries `thread_id`, `run_id`, the markdown `reply`, and the `tool_calls` the
agent made. Send that `thread_id` back on the next request and it remembers the
conversation.

---

## The agent

### The graph

[`app/agent/graph.py`](app/agent/graph.py) builds a **ReAct loop**: the model reasons,
calls a tool, reads the result, and loops until it has enough to answer.

```python
agent = create_agent(
    model=build_model(),          # timeout + bounded retries, both non-negotiable
    tools=TOOLS,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,    # injected: Postgres in the API, in-memory in the CLI
)
```

*Why a loop and not fixed stages?* A travel request has no fixed shape. "Plan Bali for 3
days" needs two searches; "is my flight delayed" needs one lookup and no itinerary at all.
A `research → itinerary → budget` StateGraph would run all three every time. Reach for a
hand-assembled `StateGraph` only when the stages become genuinely fixed.

`MODEL_NODE_NAME` is exported from this module because the streaming endpoint filters on
it — see [Streaming contract](#streaming-contract).

### The tools

Both live in [`app/tools/`](app/tools/) and follow one rule: **a tool never raises into the
graph.** An exception aborts the entire run and the user sees nothing; a returned error
*string* lets the model apologise, adapt, and carry on.

**`search_flights`** — live flight status from AviationStack: airline, flight number,
status, terminal, gate, scheduled time, delay.

The hard part is turning what a model says into an airport code. `"Bali"`, `"Japan"` and
`"NRT"` all have to work, so resolution is layered:

1. An exact 3-letter IATA code
2. A curated city map (`bali → DPS`, `tokyo → NRT`)
3. Country → primary hub, via `pycountry` (`Japan → NRT`)
4. A scored fuzzy match across the full `airportsdata` set

> The curated layer exists because the generic search resolves **"bali" to Bali, Cameroon
> (BLC)** instead of Denpasar. Adding a city there is a one-line fix.

Unresolvable input returns an actionable error to the model rather than silently widening
the query — a worldwide flight dump is worse than an honest failure. Exception messages are
never interpolated into output, because they contain the request URL and the URL contains
the API key.

**`web_search`** — Tavily, five results per call, each with title, URL and snippet. That
shape is what makes citation possible. The client is built lazily behind an `lru_cache`, so
a missing key becomes a recoverable message at call time instead of a traceback at boot.

Each tool's **docstring is the routing logic** — in a ReAct loop the model chooses tools by
reading them. That's why `web_search`'s docstring enumerates visas, weather, transport,
fares and safety, and even models a good query.

### The prompt is a guardrail

[`app/agent/prompts.py`](app/agent/prompts.py) is not just a persona. **AviationStack
returns flight status and no fares at all**, and a model shown a flight schedule will
happily quote a price for it. Five layers stop that:

| Layer | Where |
|---|---|
| `Never quote a price from this tool's output` | The `search_flights` docstring — read at call time |
| Five explicit rules: never invent a price, flight number, departure time or opening hour; label fares as estimates; cite URLs; report tool failures plainly; respect the budget | The system prompt |
| Fare questions routed to `web_search` instead | Prompt + docstrings — a legitimate path, not just a prohibition |
| Empty results explain *why* they're empty and name the alternative | The tools' return strings |
| Every tool call is shown to the user in the UI | The frontend's tool trace |

The prompt also defines the **output contract**: `### Day N` headings with
Morning / Afternoon / Evening / Stay, then a budget table and a "Good to Know" block. And
it bounds requirement-gathering — ask for what's missing, at most two questions at a time,
and start as soon as there's enough to be useful.

**Changing the prompt changes the product.** Its module docstring says why each rule
exists, so a load-bearing rule doesn't get softened by accident.

---

## API reference

Everything is under `/api`. All of it requires a session cookie except `signup`, `login`,
and the Stripe webhook.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness **plus a real `SELECT 1`** against Postgres. `503` when the database is unreachable |
| `POST` | `/api/auth/signup` | Create an account and sign in. `409` if the email exists |
| `POST` | `/api/auth/login` | Exchange credentials for a session cookie |
| `POST` | `/api/auth/logout` | Revoke the current session. Safe when already signed out |
| `GET` | `/api/auth/me` | The signed-in user |
| `POST` | `/api/chat` | Run one turn, return the complete reply |
| `POST` | `/api/chat/stream` | Run one turn, stream tokens and tool calls over SSE |
| `GET` | `/api/threads` | The caller's threads, most recently used first |
| `GET` | `/api/threads/{id}` | Full message history for a thread |
| `PATCH` | `/api/threads/{id}` | Rename a thread |
| `DELETE` | `/api/threads/{id}` | Delete a thread and its checkpointed messages |
| `POST` | `/api/feedback` | 👍/👎 on a run → LangSmith. Returns `202` immediately |
| `GET` | `/api/billing/status` | Plan, turns used, and when the allowance resets |
| `POST` | `/api/billing/checkout` | A Stripe Checkout URL for the Pro subscription |
| `POST` | `/api/billing/portal` | A Stripe customer-portal URL — cancel, change card, invoices |
| `POST` | `/api/billing/webhook` | Stripe's callback. No session; trusted by signature |

The request and response models are in [`app/schemas.py`](app/schemas.py) — that file is
the contract the frontend's TypeScript types mirror. `ChatRequest` uses `extra="forbid"`,
so a client sending a stale field fails loudly instead of having it ignored.

**Status codes worth knowing:**

| Code | Means |
|---|---|
| `401` | No valid session — sign in |
| `402` | Signed in, but the monthly allowance is spent. **Not 403**, so the client can tell "log in" from "pay" |
| `404` | The thread doesn't exist **or isn't yours** — ids can't be probed for existence |
| `429` | Rate limited |

### Threads

Omit `thread_id` on the first message; the response carries the one the server minted. Send
it back on every following request and the agent has the conversation.

```bash
curl -b cookies.txt -X POST localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Make day 2 cheaper","thread_id":"<the id you got back>"}'
```

The sidebar title is derived from the first message, cut at a word boundary
(`title_from_message`).

### Feedback

Every reply carries a `run_id`. Send it back with a score to attach feedback to that exact
LangSmith trace:

```bash
curl -b cookies.txt -X POST localhost:8000/api/feedback \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<run_id>","score":0,"comment":"wrong airport"}'
```

Filtering LangSmith to thumbs-down traces then gives you **a bug queue ranked by real user
pain**. This is the single highest-value thing in the observability setup.

---

## Streaming contract

`POST /api/chat/stream` returns Server-Sent Events in this order:

```
event: metadata     data: {"thread_id":"…","run_id":"…"}      once, first
event: token        data: {"content":"…"}                     repeatedly, as the model writes
event: tool_start   data: {"name":"…","args":{…}}             when the agent calls a tool
event: tool_end     data: {"name":"…","preview":"…"}          when it returns (200-char preview)
event: done         data: {"thread_id":"…","run_id":"…"}      once, last
event: error        data: {"message":"…","run_id":"…"}        instead of tokens, on failure
```

**`done` is always the final frame, including after `error`.**

Two things clients get wrong:

**Failures arrive in-band, not as a status code.** By the time the agent runs, the HTTP
status is already `200` — so the client must watch for an `error` frame. (This is also why
the endpoint catches exceptions *inside* the generator: raising after the response has
started sends a truncated body under a success code, and the client hangs forever.)

**`EventSource` cannot be used**, because this is a POST and `EventSource` only issues GET.
Read the body stream instead:

```ts
const res = await fetch("/api/voyanta/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message, thread_id: threadId }),
});

const reader = res.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  const frames = buffer.split("\n\n");
  buffer = frames.pop()!;                 // keep the incomplete frame for the next read
  for (const frame of frames) {
    const event = frame.match(/^event: (.*)$/m)?.[1];
    const data = JSON.parse(frame.match(/^data: (.*)$/m)?.[1] ?? "{}");
    if (event === "token") append(data.content);
    if (event === "metadata") { setThreadId(data.thread_id); setRunId(data.run_id); }
  }
}
```

> **That `buffer.pop()` is not optional.** A frame is only complete once its blank-line
> terminator has arrived; anything after the last one is a partial frame. Dropping it is
> the classic source of mysteriously missing tokens under load.

Replies are **markdown** — render with something like `react-markdown`.

**Server-side detail worth knowing if you extend the graph:** LangGraph's `messages` stream
carries every message in the graph, including `ToolMessage`s and anything a future
LLM-backed tool emits. The endpoint filters on `AIMessageChunk` **and**
`langgraph_node == "model"`, so only the actual answer reaches the user's screen.

---

## Data model

LangGraph's checkpointer creates and owns its own tables for message history. It has **no
concept of who a thread belongs to or what it's called** — so
[`app/db/schema.sql`](app/db/schema.sql) adds exactly that, and nothing more.

| Table | Holds |
|---|---|
| `users` | Email, Argon2 password hash, plan, Stripe ids |
| `sessions` | `token_hash` (never the token), user, expiry |
| `threads` | **`id` is the LangGraph `thread_id`**, plus owner, title, timestamps |
| `usage_counters` | One row per user per `YYYY-MM`, holding turns used |
| `stripe_events` | Processed event ids, so a redelivered webhook is a no-op |

One identifier spanning both systems is what makes `threads` the ownership index the
checkpoint tables lack.

**The schema is applied on every boot**, mirroring how the checkpointer sets up its own
tables. Every statement must therefore stay idempotent (`CREATE TABLE IF NOT EXISTS`,
`ADD COLUMN IF NOT EXISTS`). Reach for Alembic when a column needs to *change shape* rather
than merely appear.

---

## Auth & security

**Authorization lives here, not in the frontend.** This API is reachable on its own, so a
check that only runs in Next.js protects nothing. Every thread query filters on the
session's `user_id` **in the SQL itself** ([`app/threads/repository.py`](app/threads/repository.py)),
so there is no code path that reads a thread without proving ownership. Next.js only does
an optimistic cookie check to avoid flashing the app at a signed-out visitor; deleting it
would change nothing about who can read what.

**Sessions are opaque tokens, stored hashed.** The token is random and carries no claims —
nothing to sign, no secret to rotate. Only its SHA-256 is stored, so a database dump yields
no usable session. The cookie is `httponly`, `samesite=lax`, and `secure` outside `dev`.
It sets **no domain on purpose**, so it defaults to the host the browser actually saw —
which is the Next.js origin, not this API's.

**Login timing is equalised.** When the email is unknown, the password is verified against
a dummy hash anyway, so a failed login costs the same either way. Without it, response time
tells an attacker which emails are registered.

**Tracebacks never reach a client.** A global exception handler returns
`{"error": "Internal server error", "request_id": "…"}` and puts the detail in the log,
where that same `request_id` makes it findable.

---

## Billing

Every account gets `FREE_TURNS_PER_MONTH` turns. **A turn is one message and the reply it
produces — not tokens.** Tokens are the real cost, but nobody can look at "140,000 left" and
know whether that is a lot. Token totals still go to LangSmith; they just don't gate
anything.

Past the allowance, the chat endpoints answer **402 Payment Required** with a human
explanation, and the client raises its upgrade dialog.

> **Leaving the Stripe keys blank is a supported mode.** Turns are still counted, but never
> refused — `billing_enabled` requires all three keys. A cap with no way to pay past it is
> not a business model, it is an outage.

### Setting it up

1. Create a **recurring** price in Stripe (a `price_…`, not a `prod_…`) → `STRIPE_PRICE_ID`.
2. Put the secret key in `STRIPE_SECRET_KEY`. Test keys are free.
3. Forward webhooks to your local API:

   ```bash
   stripe listen --forward-to localhost:8000/api/billing/webhook
   ```

   Copy the `whsec_…` it prints into `STRIPE_WEBHOOK_SECRET`. In production, use the
   endpoint's signing secret from the dashboard instead.
4. Restart. `GET /api/billing/status` now reports `billing_enabled: true`.

Test the whole loop with card `4242 4242 4242 4242`, any future expiry, any CVC.

### Two rules the integration depends on

**Point Stripe at the API directly, never at the Next.js proxy.** The signature is computed
over the exact bytes of the body, and a proxy that re-encodes JSON on the way through
invalidates it. Every other browser call goes through the proxy; this one does not.

**Access is granted by webhook, never by the browser returning from Checkout.** The success
URL is a redirect the user controls — it can be opened directly, replayed, or never visited
at all after a perfectly good payment. Only the webhook is Stripe telling the *server* what
happened.

Each webhook also **re-fetches the subscription** rather than trusting the payload it
arrived with, because Stripe does not promise delivery order: an older
`subscription.updated` can land after a newer one. Re-fetching makes order irrelevant.
Duplicate deliveries are absorbed by the `stripe_events` table.

### Deliberate choices

- **A turn is reserved *before* the model runs**, in a single conditional `UPSERT`. Counting
  afterwards would let two simultaneous requests both read "19 used" and both proceed. A run
  that fails before producing anything hands its turn back; a cancelled one does not, because
  the tokens were still bought.
- **`past_due` keeps access.** Stripe retries a failed charge for about two weeks, and most
  failures are an expired card rather than a decision to stop paying. `unpaid` is where
  those retries give up — that does lose access.
- **No reset job.** The counter is keyed `YYYY-MM`, so a new month is a new key and the old
  row simply stops being read. Nothing to schedule, nothing to fail.

### Two Stripe gotchas that will bite you

**The product needs a `tax_code`.** Managed Payments is on by default for new accounts and
rejects a Checkout session whose product has none — `Invalid line_items[0]: the product tax
code is missing`. The Pro product is set to `txcd_10103000` (SaaS, personal use); change it
if your accountant disagrees. The alternative is opting out per session with
`managed_payments[enabled]=false`, which also gives up Stripe's tax handling.

**Prices are shown in the customer's local currency.** Adaptive Pricing converts at
checkout, so a Bangladeshi customer sees BDT even though the price is USD and
`PRO_PRICE_LABEL` says `$15/month`. The subscription is still billed in USD. If that
mismatch matters, turn Adaptive Pricing off or make the label currency-aware.

---

## Observability & debugging

Tracing itself needs no code — LangChain reads `LANGSMITH_*` from the environment.
[`app/observability.py`](app/observability.py) adds what makes traces *useful*:

- **Every run is tagged** with `thread_id`, `user_id`, `app_version`, `model` and
  `environment`. `thread_id` goes into both `configurable` **and** `metadata`, because
  LangSmith groups runs into conversation Threads by the metadata key.
- **The `run_id` is generated up front.** A post-hoc collector would hand it over only after
  the response is flushed — too late to tell a streaming client which trace produced the
  answer it is reading.
- **Feedback runs in a `BackgroundTask`**, so a slow or failing call to an observability
  vendor never makes the product feel slow.

### Following one bad answer end to end

Logs are JSON ([`app/logging_config.py`](app/logging_config.py)) and every line carries a
`request_id`; lines produced during a turn also carry the `run_id`.

```
user reports a bad answer
   → find the log line (X-Request-ID is returned on every response)
   → it carries the run_id
   → open that exact LangSmith trace: every prompt, tool call and tool result
```

Without that link you are grepping timestamps.

> **⚠️ Import order in `app/api/main.py` is load-bearing.** `app.config` is imported first
> because it calls `load_dotenv()`, and LangChain reads `LANGSMITH_*` at import time. Import
> LangChain before it and **tracing silently stays off** — the worst kind of failure,
> because everything still appears to work.

---

## Project layout

```
backend/
├── .env                        Your keys. Git-ignored, loaded relative to this directory
├── Dockerfile                  Multi-stage; deps cached in their own layer, runs as non-root
├── app/
│   ├── config.py               Settings + load_dotenv() + the macOS cert fix
│   ├── logging_config.py       JSON logs carrying request_id + run_id
│   ├── observability.py        LangSmith run config and feedback
│   ├── schemas.py              THE HTTP CONTRACT + LangChain message serialisation
│   ├── agent/
│   │   ├── graph.py            create_agent(...) — the ReAct loop
│   │   └── prompts.py          The system prompt / guardrail
│   ├── tools/
│   │   ├── flight_tool.py      Location resolution + AviationStack
│   │   └── tavily_tool.py      Web search
│   ├── auth/                   passwords.py (Argon2) · sessions.py (hashed tokens) · routes.py
│   ├── billing/                quota.py (atomic reservation) · stripe_gateway.py
│   ├── threads/repository.py   Thread queries — every one filters on user_id
│   ├── db/schema.sql           Idempotent, applied on every boot
│   └── api/
│       ├── main.py             App, lifespan, middleware, /health
│       ├── deps.py             require_user / require_turn — the two gates
│       ├── limiter.py          Shared rate limiter
│       └── routes/             chat · threads · feedback · billing
└── scripts/cli_chat.py         Terminal REPL — in-memory, no database needed
```

**Where to start reading:** `app/agent/prompts.py` → `app/agent/graph.py` →
`app/api/routes/chat.py`. That's the whole product in three files.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Server won't start: `DATABASE_URL is not set` | Voyanta persists threads in Postgres. Set it, or use `scripts/cli_chat.py` for an in-memory session. |
| `/health` returns `503`, `"database":"unreachable"` | The API is up but Postgres isn't. Check the connection string and that the database accepts connections. |
| Nothing appears in LangSmith | Either `LANGSMITH_API_KEY` is unset (the boot log warns), or something imported LangChain before `app.config`. Check the first import in `main.py`. |
| Agent says a key is missing, mid-conversation | Working as designed — `TAVILY_API_KEY` / `AVIATIONSTACK_API_KEY` is unset, and the tool reports it to the model instead of crashing the run. |
| `Could not resolve 'X' to an airport` | The layered resolver found nothing. Use a major city or an IATA code, or add the city to `CITY_MAIN_AIRPORT` in `flight_tool.py`. |
| Flights come back empty for a valid route | AviationStack only reports flights currently in the live schedule. A real route can legitimately be empty; the tool's message says so and points at `web_search`. |
| `402` on every chat request | The monthly allowance is spent. Raise `FREE_TURNS_PER_MONTH`, upgrade the account, or wait for the month to roll over. |
| Stripe webhook returns `400` signature error | Stripe is pointed at the Next.js proxy instead of this API, or `STRIPE_WEBHOOK_SECRET` doesn't match this endpoint. |
| Payment succeeded but the plan still says Free | The webhook hasn't landed. Confirm `stripe listen` is running and check the API log for the event. |
| TLS failures calling APIs on macOS | Handled: `config.py` points `SSL_CERT_FILE` at `certifi` on Darwin. If you bypass `config.py`, you lose that. |
| Stream ends with no tokens | Look for an `error` frame — failures are reported in-band, since the status is already `200`. |

---

## Known limits

- **No password reset, and no email verification.**
- **Rate limiting keys on IP**, so behind a proxy every user shares one bucket. Per-user
  limiting is the fix.
- **No automated eval suite yet.** Quality rests on the prompt guardrails and the LangSmith
  👍/👎 loop. The natural next step is a golden set of requests scored for citation coverage
  and fabricated-figure rate — the feedback plumbing already exists to feed it.
- **No fares from `search_flights`, by design.** AviationStack has no pricing data. Swapping
  in a pricing API (Amadeus, say) means changing exactly one function: `_fetch_flights`.
- **LangSmith traces include full user messages.** Review before handling personal or
  payment data.
