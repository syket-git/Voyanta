# Voyanta — Backend

A tour-planner agent built with **LangGraph**, exposed as an HTTP API for the frontend in
[`../frontend`](../frontend) to consume.

The agent plans day-by-day itineraries. It has two tools: live flight lookup
(AviationStack) and web search (Tavily). Conversations are checkpointed in Postgres, so a
thread survives a server restart, and every run is traced to LangSmith.

> **LangGraph vs LangGraph Platform** — this project uses the LangGraph *library* to build
> the agent, but not LangGraph *Platform* (the hosted deployment product with
> `langgraph.json` and `langgraph dev`). The HTTP layer here is hand-written FastAPI, so
> you own the JSON contract your frontend codes against.

---

## Setup

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/), plus a reachable Postgres.
Every command below runs from this `backend/` directory.

```bash
cd backend
uv sync
cp .env.example .env     # then fill in your keys
```

Keys you need: `OPENAI_API_KEY`, `TAVILY_API_KEY`, `AVIATIONSTACK_API_KEY`,
`DATABASE_URL`, and `LANGSMITH_API_KEY` for tracing.

The `STRIPE_*` keys are optional — see [Billing](#billing). Without them the app runs
normally and simply never charges anyone.

## Run

```bash
# API server
uv run uvicorn app.api.main:app --reload --port 8000

# or a terminal REPL that needs no database (useful for debugging the agent alone)
uv run python scripts/cli_chat.py
```

Interactive API docs: <http://localhost:8000/docs>

---

## API

Everything under `/api` except `/api/auth/signup` and `/api/auth/login` requires a
session cookie.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness plus a real `SELECT 1` against Postgres |
| `POST` | `/api/auth/signup` | Create an account and sign in |
| `POST` | `/api/auth/login` | Exchange credentials for a session cookie |
| `POST` | `/api/auth/logout` | Revoke the current session |
| `GET` | `/api/auth/me` | The signed-in user |
| `POST` | `/api/chat` | Run one turn, return the full reply |
| `POST` | `/api/chat/stream` | Run one turn, stream tokens over SSE |
| `GET` | `/api/threads` | The caller's threads, most recent first |
| `GET` | `/api/threads/{thread_id}` | Full message history for a thread |
| `PATCH` | `/api/threads/{thread_id}` | Rename a thread |
| `DELETE` | `/api/threads/{thread_id}` | Delete a thread and its messages |
| `POST` | `/api/feedback` | Thumbs up/down on a run → LangSmith |
| `GET` | `/api/billing/status` | Plan, turns used, and when the allowance resets |
| `POST` | `/api/billing/checkout` | Stripe Checkout URL for the Pro subscription |
| `POST` | `/api/billing/portal` | Stripe customer portal URL — cancel, card, invoices |
| `POST` | `/api/billing/webhook` | Stripe's callback. No session; trusted by signature |

### Threads

Omit `thread_id` on the first request; the response carries the one the server minted.
Send it back on every following request and the agent remembers the conversation.

```bash
curl -X POST localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Plan a 3 day Bali trip from Dhaka","thread_id":"demo-1"}'
```

### Streaming

`POST /api/chat/stream` returns Server-Sent Events in this order:

```
metadata   {thread_id, run_id}          once, first
token      {content}                    repeatedly, as the model writes
tool_start {name, args}                 when a tool is called
tool_end   {name, preview}              when it returns
done       {thread_id, run_id}          once, last
error      {message, run_id}            instead of tokens, on failure
```

`done` is always the final frame, including after `error`. Failures are reported in-band:
the HTTP status is already 200 by the time the agent runs, so the client must watch for
an `error` frame rather than rely on the status code.

`EventSource` cannot be used because this is a POST. Read the body stream instead:

```ts
const res = await fetch("http://localhost:8000/api/chat/stream", {
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
  buffer = frames.pop()!;                 // keep the incomplete frame for next read
  for (const frame of frames) {
    const event = frame.match(/^event: (.*)$/m)?.[1];
    const data = JSON.parse(frame.match(/^data: (.*)$/m)?.[1] ?? "{}");
    if (event === "token") append(data.content);
    if (event === "metadata") { setThreadId(data.thread_id); setRunId(data.run_id); }
  }
}
```

Replies are markdown — render them with something like `react-markdown`.

### Feedback

Every reply carries a `run_id`. Send it back with a score to attach user feedback to that
LangSmith trace:

```bash
curl -X POST localhost:8000/api/feedback \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"<run_id>","score":0,"comment":"wrong airport"}'
```

Filtering LangSmith to thumbs-down traces gives you a bug queue ranked by real user pain.

---

## Billing

Every account gets `FREE_TURNS_PER_MONTH` turns. A turn is one message and the reply it
produces — not tokens. Tokens are the real cost, but nobody can look at "140,000 left"
and know whether that is a lot.

Past the allowance the chat endpoints answer **402 Payment Required**, and the client
raises the upgrade dialog. 402 rather than 403 so the client can tell "you are not signed
in" from "you are, but this costs money".

**Leaving the Stripe keys blank is a supported mode.** Turns are still counted, but never
refused — `billing_enabled` requires all three keys, and a cap with no way to pay past it
is not a business model, it is an outage.

### Setting it up

1. Create a **recurring** price in Stripe (a `price_...`, not a `prod_...`) and put it in
   `STRIPE_PRICE_ID`.
2. Put the secret key in `STRIPE_SECRET_KEY`. Test keys are fine and cost nothing.
3. Forward webhooks locally:

   ```bash
   stripe listen --forward-to localhost:8000/api/billing/webhook
   ```

   Copy the `whsec_...` it prints into `STRIPE_WEBHOOK_SECRET`. In production this is the
   endpoint's signing secret from the dashboard instead.
4. Restart the API. `GET /api/billing/status` now reports `billing_enabled: true`.

Test the whole loop with card `4242 4242 4242 4242`, any future expiry, any CVC.

**The product needs a `tax_code`.** Managed Payments is on by default on new accounts and
rejects a Checkout session whose product has none — `Invalid line_items[0]: the product
tax code is missing`. The Pro product is set to `txcd_10103000` (SaaS, personal use);
change it if your accountant disagrees. The alternative is opting out per session with
`managed_payments[enabled]=false`, which also gives up Stripe's tax handling.

**Prices are presented in the customer's local currency.** Stripe's Adaptive Pricing
converts at checkout, so a Bangladeshi customer sees BDT even though the price is USD and
`PRO_PRICE_LABEL` says `$15/month`. The subscription is still billed in USD. If that
mismatch matters, either turn Adaptive Pricing off or make the label currency-aware.

### Two rules the integration depends on

**Point Stripe at the API directly, never at the Next.js proxy.** The signature is
computed over the exact bytes of the body; a proxy that re-encodes JSON on the way through
invalidates it. Every other browser call goes through the proxy — this one does not.

**Access is granted by webhook, never by the browser returning from Checkout.** The
success URL is a redirect the user controls: it can be opened directly, replayed, or never
visited at all after a perfectly good payment. Only the webhook is Stripe telling the
server what happened.

Each webhook also re-fetches the subscription rather than trusting the payload it arrived
with, because Stripe does not promise delivery order — an older `subscription.updated` can
land after a newer one. Re-fetching makes order irrelevant.

### Deliberate choices

- **A turn is reserved before the model runs**, in one conditional statement. Counting
  afterwards would let two simultaneous requests both read "19 used" and both proceed.
  A run that fails before producing anything hands its turn back; a cancelled one does
  not, because the tokens were still bought.
- **`past_due` keeps access.** Stripe retries a failed charge for about two weeks, and
  most failures are an expired card rather than a decision to stop paying. `unpaid` is
  where those retries give up, and that does lose access.
- **No reset job.** The counter is keyed `YYYY-MM`, so a new month is a new key and the
  old row simply stops being read. There is nothing to schedule and nothing to fail.

---

## Layout

```
backend/
├── .env                       Your keys; git-ignored, loaded relative to this directory
├── app/
│   ├── config.py              Settings; loads .env and the macOS cert fix
│   ├── logging_config.py      JSON logs carrying request_id + run_id
│   ├── observability.py       LangSmith run config and feedback
│   ├── schemas.py             The HTTP contract + LangChain message serialisation
│   ├── agent/
│   │   ├── graph.py           create_agent(...) — the ReAct loop
│   │   └── prompts.py         System prompt
│   ├── tools/
│   │   ├── flight_tool.py     Location resolution + AviationStack
│   │   └── tavily_tool.py     Web search
│   └── api/
│       ├── main.py            App, lifespan, CORS, /health
│       └── routes/            chat, threads, feedback
└── scripts/cli_chat.py        Terminal REPL, in-memory, no database needed
```

---

## Notes

**Flight prices are not available.** AviationStack returns live flight *status* — airline,
gate, delay — and no fares at all. The tool docstring and the system prompt both forbid
quoting a price from it; fare questions are routed to web search and labelled as
estimates. Swapping in a pricing API (e.g. Amadeus) means changing only `_fetch_flights`
in `app/tools/flight_tool.py`.

**Import order in `app/api/main.py` matters.** `app.config` is imported first because it
calls `load_dotenv()`, and LangChain reads `LANGSMITH_*` at import time. Import langchain
before it and tracing silently stays off.

**Authorization lives here, not in the frontend.** Every thread route filters on the
session's `user_id` in the SQL itself, so there is no path that reads a thread without
proving ownership. Another user's thread returns 404 rather than 403, so ids cannot be
probed for existence. Next.js only does an optimistic cookie check to avoid flashing the
app at a signed-out visitor — deleting that check would change nothing about who can read
what.

**Sessions are opaque tokens, stored hashed.** There is no signing secret to rotate; the
`sessions` table holds a SHA-256, so a database dump yields no usable session.

**The schema is applied on every boot** from `app/db/schema.sql`, which mirrors how the
checkpointer sets up its own tables. Every statement must stay idempotent. Reach for
Alembic when a column needs to change shape rather than merely appear.

**Still missing:** password reset, email verification, and per-user rate limiting — the
limiter keys on IP, so behind a proxy every user shares one bucket.

**LangSmith traces include full user messages.** Review before handling personal or
payment data.
