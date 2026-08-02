# Voyanta

A tour-planner agent that turns a vague travel wish into a concrete, day-by-day
itinerary. It looks up live flight status (AviationStack) and searches the web (Tavily),
keeps each conversation in Postgres so threads survive a restart, and traces every run to
LangSmith.

```
Voyanta/
├── backend/     LangGraph agent + FastAPI HTTP API (Python 3.14, uv)
└── frontend/    Next.js 16 + Tailwind v4 + shadcn/ui (pnpm)
```

The two halves are independent: the backend is a plain JSON/SSE API, and the frontend
proxies to it server-side, so either can be deployed on its own.

## Getting started

Two terminals. Backend first — the frontend has nothing to talk to without it.

```bash
cd backend
uv sync
cp .env.example .env     # then fill in your keys
uv run uvicorn app.api.main:app --reload --port 8000
```

```bash
cd frontend
pnpm install
pnpm dev
```

The app is at <http://localhost:3000>, the API docs at <http://localhost:8000/docs>.

See [backend/README.md](backend/README.md) for the endpoint reference and SSE contract,
and [frontend/README.md](frontend/README.md) for how the client consumes it.

## Conventions

- Each directory owns its own dependencies, config and README. There is no shared build
  or workspace tooling — run commands from inside `backend/` or `frontend/`.
- Secrets live in a git-ignored `.env` beside the code that reads them, never at the
  repository root.
- The browser never calls FastAPI directly. Requests go through the Next.js proxy at
  `/api/voyanta/*`, which keeps them same-origin — so CORS does not apply, and the
  backend's origin stays server-side.
