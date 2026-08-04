# Voyanta — Frontend

Next.js 16 (App Router) + Tailwind v4 + shadcn/ui.

| Route              | What it is                                            |
| ------------------ | ----------------------------------------------------- |
| `/`                | Marketing page, public                                |
| `/login`, `/signup`| Email and password auth                               |
| `/chat`            | A new conversation                                    |
| `/chat/[threadId]` | An existing thread, with the sidebar of past threads  |

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
Nothing in the browser knows the backend's address, requests are same-origin so **CORS
never applies**, and the session cookie is forwarded in both directions.

Each HTTP verb must be exported by name from that route. Next answers **405** for any
verb it does not export, and the request never reaches the backend.

The streaming turn is a `POST`, so `EventSource` cannot be used; it only issues `GET`.
`lib/voyanta.ts` reads `response.body` and splits SSE frames on the blank-line terminator
instead, buffering whatever partial frame is left at the end of each chunk.

## Billing

The sidebar footer shows the usage meter. When the backend answers **402** the chat hook
calls `promptUpgrade`, and `BillingProvider` raises the upgrade dialog carrying the
backend's own wording — the client never decides that the allowance is spent, it only
reacts to being told.

Two details worth keeping:

- **The upgrade button only appears when `billing_enabled` is true.** Offering an upgrade
  that cannot complete is worse than showing no upgrade at all.
- **After Checkout the provider polls `/billing/status` briefly.** Stripe's webhook and
  the browser redirect race each other and the redirect usually wins, so without the poll
  the user lands back on a page still reading "Free" moments after paying.

## Auth

`proxy.ts` (Next 16's rename of middleware) redirects signed-out visitors away from
`/chat`, but that is **only** to avoid flashing the app — Next's own docs say Proxy is not
an authorization mechanism. `app/chat/layout.tsx` verifies the session against the backend
before rendering, and the backend authorises every request regardless. Removing the proxy
check would leak nothing.

## Layout

```
proxy.ts                        Optimistic redirect for signed-out visitors
app/
├── page.tsx                    Marketing page
├── login/, signup/             Auth pages
├── chat/layout.tsx             Session check + sidebar shell
├── chat/page.tsx               New conversation
├── chat/[threadId]/page.tsx    An existing thread
├── api/voyanta/[...path]/      Proxy to FastAPI
├── layout.tsx                  Fonts, dark theme, toaster
└── globals.css                 Design tokens
components/
├── departure-board.tsx         The landing page's signature element
├── markdown.tsx                Renders the agent's markdown replies
├── auth/auth-form.tsx          Shared by login and signup
├── chat/                       workspace, sidebar, message-row, composer, tool-trace
└── ui/                         shadcn primitives
hooks/use-chat.ts               Streaming state machine
lib/voyanta.ts                  Typed client for the backend contract
lib/session.ts                  Server-side session read
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
