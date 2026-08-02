# Voyanta — Frontend

Not started yet. Scaffold your framework of choice directly into this directory.

## What it needs to do

Talk to the backend API documented in [../backend/README.md](../backend/README.md):

- `POST /api/chat/stream` for a turn, reading the SSE body stream. `EventSource` will not
  work — it only issues GET requests, so read `response.body` with a reader instead. The
  backend README has a working TypeScript snippet.
- Hold on to the `thread_id` from the first `metadata` frame and send it back on every
  following turn; that is what gives the agent its memory.
- Keep each reply's `run_id` so a thumbs up/down can be posted to `POST /api/feedback`.
- Render replies as markdown — the agent answers with headings, tables and lists.

## Before it will connect

Add the dev server's origin to `CORS_ORIGINS` in `backend/.env` (it already allows
`http://localhost:3000` and `http://127.0.0.1:3000`), and point the client at
`http://localhost:8000`.

The API has no authentication. Keep it on localhost, or put an authenticated gateway in
front of both halves before deploying anywhere public.
