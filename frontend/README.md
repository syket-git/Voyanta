# Voyanta — Frontend

Next.js 16 (App Router) + Tailwind v4 + shadcn/ui. Two routes:

| Route   | What it is                                                     |
| ------- | -------------------------------------------------------------- |
| `/`     | Marketing page                                                  |
| `/chat` | The app — streaming chat against the [backend](../backend)      |

## Run

The backend must be running first. From the repo root:

```bash
cd backend && uv run uvicorn app.api.main:app --reload --port 8000
```

Then, in another terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

<http://localhost:3000>

Point it at a backend somewhere other than `http://127.0.0.1:8000` with
`VOYANTA_API_URL` in `frontend/.env.local`.

## How it talks to the backend

Every call goes through `app/api/voyanta/[...path]/route.ts`, which proxies to FastAPI.
Nothing in the browser knows the backend's address.

That is worth keeping. It makes requests same-origin, so **CORS never applies** and the
backend's `CORS_ORIGINS` is irrelevant in this setup. It is also the only place a session
could be attached: the backend trusts `user_id` from the request body, so once there is
auth, the proxy is where `user_id` gets set — never the client.

The streaming turn is a `POST`, so `EventSource` cannot be used; it only issues `GET`.
`lib/voyanta.ts` reads `response.body` and splits SSE frames on the blank-line terminator
instead, buffering whatever partial frame is left at the end of each chunk.

## Layout

```
app/
├── page.tsx                    Marketing page
├── chat/page.tsx               The app
├── api/voyanta/[...path]/      Proxy to FastAPI
├── layout.tsx                  Fonts, dark theme, toaster
└── globals.css                 Design tokens
components/
├── departure-board.tsx         The landing page's signature element
├── markdown.tsx                Renders the agent's markdown replies
├── chat/                       chat-panel, message-row, composer, tool-trace
└── ui/                         shadcn primitives
hooks/use-chat.ts               Streaming state machine
lib/voyanta.ts                  Typed client for the backend contract
```

## Notes

**shadcn has no chat component.** The official registry ships primitives, not a chat
block, so the chat is composed here from `button`, `textarea`, `collapsible` and the
rest. This project uses the **Base UI** variant, which means `render={<Link />}` where
Radix-based shadcn would use `asChild`.

**Markdown is re-parsed on a timer, not per token.** Tokens arrive far faster than anyone
reads, so `use-chat.ts` accumulates them in a ref and flushes to state every 60ms. Parsing
on each token makes long replies stutter.

**Design tokens live in `globals.css`.** The palette is a departure board: ink background,
one sodium-amber accent, hairline rules. There is no light theme — `<html>` is pinned to
`dark`. Adding one means filling in a `:root` light block and removing that class.
