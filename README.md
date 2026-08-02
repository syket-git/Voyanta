# Voyanta

A tour-planner agent built with **LangGraph**, exposed as an HTTP API for a separate
React/Next.js frontend to consume.

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

```bash
uv sync
cp .env.example .env     # then fill in your keys
```

Keys you need: `OPENAI_API_KEY`, `TAVILY_API_KEY`, `AVIATIONSTACK_API_KEY`,
`DATABASE_URL`, and `LANGSMITH_API_KEY` for tracing.

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

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness plus a real `SELECT 1` against Postgres |
| `POST` | `/api/chat` | Run one turn, return the full reply |
| `POST` | `/api/chat/stream` | Run one turn, stream tokens over SSE |
| `GET` | `/api/threads/{thread_id}` | Full message history for a thread |
| `DELETE` | `/api/threads/{thread_id}` | Delete a thread |
| `POST` | `/api/feedback` | Thumbs up/down on a run → LangSmith |

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

## Layout

```
app/
├── config.py          Settings; loads .env and the macOS cert fix
├── logging_config.py  JSON logs carrying request_id + run_id
├── observability.py   LangSmith run config and feedback
├── schemas.py         The HTTP contract + LangChain message serialisation
├── agent/
│   ├── graph.py       create_agent(...) — the ReAct loop
│   └── prompts.py     System prompt
├── tools/
│   ├── flight_tool.py Location resolution + AviationStack
│   └── tavily_tool.py Web search
└── api/
    ├── main.py        App, lifespan, CORS, /health
    └── routes/        chat, threads, feedback
scripts/cli_chat.py    Terminal REPL, in-memory, no database needed
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

**LangSmith traces include full user messages.** Fine here; review before handling
personal or payment data.

**There is no authentication.** Any caller who knows a `thread_id` can read or delete
that conversation, and `user_id` is whatever the client claims. Put this behind an
authenticated gateway, or add auth here, before exposing it publicly. Rate limiting keys
on the client IP, so it also needs a trusted-proxy header behind a load balancer.
