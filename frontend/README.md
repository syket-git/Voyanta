# Voyanta — Frontend

The web app: a marketing page, auth, and a streaming chat workspace where you watch the
agent call its tools.

Built with **Next.js 16 (App Router)**, **React 19**, **Tailwind v4** and **shadcn/ui**. It
talks to the FastAPI backend in [`../backend`](../backend) — and only ever through a
server-side proxy, never directly from the browser.

**New here? Read [How data flows](#how-data-flows) first — the proxy is the one non-obvious
thing about this app. Then [Run](#run).**

---

## Contents

1. [Routes](#routes) · [Run](#run)
2. [How data flows](#how-data-flows) — the proxy, and why it exists
3. [Auth](#auth) — three layers, only one of which protects anything
4. [Streaming](#streaming) — how a reply arrives token by token
5. [Billing UI](#billing-ui) · [Design system](#design-system)
6. [Project layout](#project-layout) · [Troubleshooting](#troubleshooting) · [Building for production](#building-for-production)

---

## Routes

| Route | What it is | Auth |
|---|---|---|
| `/` | Marketing page — the departure board, the tools, the rules the agent follows | Public |
| `/login`, `/signup` | Email and password | Public (redirects to `/chat` if signed in) |
| `/chat` | A new conversation | Signed in |
| `/chat/[threadId]` | An existing thread, with the sidebar of past trips | Signed in |

## Run

**The backend must be running first** — this app has nothing to talk to without it.

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

### Configuration

There is exactly one environment variable:

| Variable | Default | What it does |
|---|---|---|
| `VOYANTA_API_URL` | `http://127.0.0.1:8000` | Where the backend lives. **Server-side only** — it is read by the proxy route and by the session check, and never reaches the browser. |

Set it in `frontend/.env.local` to point at a backend somewhere else. In Docker Compose
it's set to `http://backend:8000`, so the API never leaves the compose network.

---

## How data flows

**The browser never calls FastAPI directly.** Every request goes through a Next.js route
handler at `/api/voyanta/*`, which forwards it to the backend:

```
Browser                     Next.js server                    FastAPI
   │                              │                              │
   │  fetch("/api/voyanta/chat/stream")                          │
   │─────────────────────────────▶│                              │
   │                              │  forwards method, body,      │
   │                              │  cookie, x-request-id        │
   │                              │─────────────────────────────▶│
   │                              │                              │
   │                              │◀── SSE stream, set-cookie ───│
   │◀─── streamed straight through│                              │
```

Three things this buys you:

- **The backend's address never reaches the client.** Only the Next.js server knows it.
- **CORS never applies.** Requests are same-origin, so there is no preflight and no origin
  list to keep in sync.
- **One place to attach cross-cutting concerns** — the session cookie, request ids, and
  anything added later.

The proxy is [`app/api/voyanta/[...path]/route.ts`](app/api/voyanta/[...path]/route.ts).
Four details in it are load-bearing:

| Detail | Why |
|---|---|
| Every HTTP verb is exported **by name** (`GET`, `POST`, `PATCH`, `DELETE`) | Next answers **405** for any verb it doesn't export, and the request never reaches the backend. Adding an endpoint that uses `PUT` means exporting `PUT`. |
| `export const dynamic = "force-dynamic"` | Streaming replies must not be cached or buffered anywhere in between. |
| `getSetCookie()`, not `get("set-cookie")` | Keeps multiple `Set-Cookie` headers separate. Reading them as one joined string corrupts any cookie whose value contains a comma. |
| `upstream.body` is returned as-is | The response is **piped, not buffered** — otherwise the SSE stream would only arrive once the whole reply finished, defeating the point. |

**The one deliberate exception:** the Stripe webhook must point at the backend directly.
Stripe's signature is computed over the exact bytes of the body, and a proxy that
re-encodes JSON invalidates it.

### The typed client

[`lib/voyanta.ts`](lib/voyanta.ts) wraps every call to `/api/voyanta/*` and mirrors the
backend's Pydantic models as TypeScript interfaces. **When `backend/app/schemas.py`
changes, this file changes with it** — that pair is the contract.

It also normalises errors: FastAPI returns validation failures as a list of per-field
objects and everything else as `detail`, so `failure()` flattens both into one string the
UI can show.

---

## Auth

There are three checks, and it's worth being precise about what each one does:

| Layer | File | What it actually protects |
|---|---|---|
| **1. Optimistic redirect** | [`proxy.ts`](proxy.ts) | **Nothing.** It only checks that a cookie *exists*, to avoid flashing the app at a signed-out visitor. Next's own docs say Proxy is not an authorization mechanism. |
| **2. Server-side session check** | [`app/chat/layout.tsx`](app/chat/layout.tsx) → [`lib/session.ts`](lib/session.ts) | Asks the backend whether the session is *valid*, so an expired or revoked cookie can't render the app shell. |
| **3. The backend** | `require_user` on every route | **This is the real one.** Every request is authorised server-side against the session table, and every thread query filters on `user_id` in the SQL. |

Delete layers 1 and 2 and **nothing leaks** — the app just looks worse for a moment. That's
the correct division of labour, and it's why the frontend never makes an authorization
decision of its own.

> `proxy.ts` is Next 16's rename of `middleware.ts`. Same file role, same `config.matcher`.

`lib/session.ts` calls the backend **directly** rather than through the proxy route, because
a server component has no origin to make a relative request against.

---

## Streaming

A reply arrives as Server-Sent Events: `metadata` → `token`* / `tool_start` / `tool_end` →
`done` (see the [SSE contract](../backend/README.md#streaming-contract) for the frames).

Two files handle it:

**[`lib/voyanta.ts`](lib/voyanta.ts) → `streamChat()`** is an async generator that reads the
response body and yields typed events.

- `EventSource` can't be used — it only issues GET, and a turn is a POST. So the body is
  read with `getReader()` and frames are split on the blank-line terminator.
- **The trailing partial frame is buffered** for the next read. A frame isn't complete until
  its `\n\n` arrives; dropping the remainder is the classic cause of mysteriously missing
  tokens under load.
- A **402** arrives as a normal JSON response, not an SSE frame, because the refusal happens
  before the stream opens. It's converted into an `error` event with `upgrade: true` — the
  one failure the reader can actually act on.

**[`hooks/use-chat.ts`](hooks/use-chat.ts)** is the state machine that turns those events
into rendered messages:

| Event | What the hook does |
|---|---|
| `metadata` | Stores the `run_id` on the message (needed for 👍/👎) and, on a first message, reports the newly minted `thread_id` |
| `token` | Appends to a **ref**, not to state |
| `tool_start` | Flushes pending text, then appends an unsettled trace row |
| `tool_end` | Finds the matching open row and settles it with the result preview |
| `error` | Marks the message failed; if `upgrade`, shows the backend's wording verbatim and raises the plan dialog |
| `done` | Final flush |

Four decisions in there are worth keeping:

- **Markdown is re-parsed on a 60ms timer, not per token.** Tokens arrive far faster than
  anyone reads. Parsing each one makes long itineraries stutter; accumulating in a ref and
  flushing on an interval keeps a 900-word plan smooth.
- **Switching threads remounts the hook via a `key`** on the workspace — React's own answer
  to "reset state when a prop changes" — rather than resetting through an effect.
- **The URL is corrected with `history.replaceState`, not a router navigation.** The backend
  mints the thread id on the first message; navigating at that moment would unmount the
  component and kill the in-flight stream.
- **Auto-scroll stops the moment the reader scrolls up.** Following the stream is helpful
  until someone is trying to re-read day 2.

The composer can `stop()` a turn — that aborts the fetch. Note that a cancelled turn stays
charged; the tokens were still bought.

---

## Billing UI

The sidebar footer shows a usage meter. When the backend answers **402**, the chat hook
calls `promptUpgrade`, and [`BillingProvider`](components/billing/billing-provider.tsx)
raises the upgrade dialog **carrying the backend's own wording**. The client never decides
that an allowance is spent — it only reacts to being told.

Three details worth keeping:

- **The upgrade button only appears when `billing_enabled` is true.** Offering an upgrade
  that cannot complete is worse than showing no upgrade at all.
- **After Checkout the provider polls `/billing/status`** six times, 1.5s apart. Stripe's
  webhook and the browser redirect race each other and the redirect usually wins — without
  the poll, a user lands back on a page still reading "Free" moments after paying, which
  reads as a failed payment. If the poll runs out it says "your plan will update in a
  moment" rather than claiming failure.
- **`redirecting` stays true on the way out to Stripe.** The page is being replaced, so
  re-enabling the button would only invite a second tab.

The meter refreshes after every turn, since the backend counted the turn before the reply
even started.

---

## Design system

The visual language is a **departure board**: ink background, one sodium-amber accent,
hairline rules, monospace uppercase row labels. The product's honest claim is *live
operational data*, so the UI looks like the board it reads from.

- **Tokens live in [`app/globals.css`](app/globals.css)** as CSS custom properties, exposed
  to Tailwind v4 through `@theme inline`. `--sodium` is the accent; change it there and it
  changes everywhere.
- **There is no light theme.** `<html>` is pinned to `dark`. Adding one means filling in a
  `:root` light block and removing that class.
- **`components/brand.tsx`** holds the wordmark and the `RuleLabel` eyebrow — the two pieces
  of identity reused across pages.

> **shadcn has no chat component.** The registry ships primitives, not a chat block, so the
> workspace is composed here from `button`, `textarea`, `collapsible`, `sidebar` and the
> rest.
>
> This project uses the **Base UI** variant of shadcn, not the Radix one. The practical
> difference: `render={<Link />}` where Radix-based shadcn would use `asChild`.

---

## Project layout

```
proxy.ts                        Optimistic redirect for signed-out visitors (Next 16's middleware)
next.config.ts                  output: "standalone" — for the Docker image
app/
├── page.tsx                    Marketing page
├── login/, signup/             Auth pages (both render components/auth/auth-form.tsx)
├── chat/layout.tsx             Real session check + providers + sidebar shell
├── chat/page.tsx               New conversation
├── chat/[threadId]/page.tsx    An existing thread
├── api/voyanta/[...path]/      THE PROXY — every backend call goes through here
├── layout.tsx                  Fonts, dark theme, toaster
└── globals.css                 Design tokens
components/
├── brand.tsx                   Wordmark + rule label
├── departure-board.tsx         The landing page's signature element
├── markdown.tsx                Renders the agent's markdown replies (react-markdown + gfm)
├── auth/auth-form.tsx          Shared by login and signup
├── chat/
│   ├── chat-workspace.tsx      Composes the hook, scroll behaviour, composer
│   ├── thread-sidebar.tsx      Past trips, rename, delete, usage meter
│   ├── threads-provider.tsx    Shared sidebar state
│   ├── message-row.tsx         One message + its 👍/👎 control
│   ├── composer.tsx            Input, send, stop
│   └── tool-trace.tsx          The collapsible "what the agent did" rows
├── billing/                    billing-provider · upgrade-dialog · usage-meter
└── ui/                         shadcn primitives (Base UI variant)
hooks/use-chat.ts               The streaming state machine
lib/voyanta.ts                  Typed client for the backend contract
lib/session.ts                  Server-side session read
```

**Where to start reading:** `lib/voyanta.ts` → `hooks/use-chat.ts` →
`components/chat/chat-workspace.tsx`. That's the whole chat experience in three files.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Cannot reach the Voyanta API. Is the backend running?` | The proxy got a connection error. Start the backend, or fix `VOYANTA_API_URL`. |
| Every request 405s | The proxy doesn't export that HTTP verb. Add it to the exports at the bottom of the route file. |
| Signed in, but immediately bounced to `/login` | The cookie exists but the backend rejected it — expired or revoked. Sign in again. |
| Reply appears all at once instead of streaming | Something is buffering: a reverse proxy without `X-Accel-Buffering: no`, or a lost `force-dynamic`. |
| Tokens visibly missing from a reply | An SSE frame was split across reads and the partial frame wasn't buffered. See `streamChat`. |
| Upgrade dialog never appears | The backend returned 402 but `upgrade` wasn't set, or `billing_enabled` is false because Stripe isn't configured. |
| Still says "Free" right after paying | The webhook is racing the redirect. The provider polls for ~9s; if Stripe's webhook never lands, check the backend log. |
| Sidebar empty after a first message | `onTurnComplete` refreshes it once the turn ends — check the browser console for a failed `/threads` call. |
| A Next.js API doesn't behave as documented online | **This is Next.js 16.** Check `node_modules/next/dist/docs/` — conventions changed, including `middleware.ts` → `proxy.ts`. |

---

## Building for production

```bash
pnpm build     # produces .next/standalone
pnpm start
```

`next.config.ts` sets `output: "standalone"`, so the build emits a self-contained server
plus only the `node_modules` it traced as reachable. The [`Dockerfile`](Dockerfile) copies
that plus `.next/static` into a slim `node:24-alpine` image and runs as a non-root user.

Remember that `VOYANTA_API_URL` is read **at runtime on the server**, so the same image can
point at different backends per environment.
