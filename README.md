# Voyanta

A tour-planner agent that turns a vague travel wish into a concrete, day-by-day
itinerary. It looks up live flight status (AviationStack) and searches the web (Tavily),
keeps each conversation in Postgres so threads survive a restart, and traces every run to
LangSmith.

```
Voyanta/
├── backend/     LangGraph agent + FastAPI HTTP API (Python 3.14, uv)
└── frontend/    Web client — not started yet
```

The two halves are independent: the backend is a plain JSON/SSE API over HTTP, so the
frontend can be built with whatever stack you choose and deployed separately.

## Getting started

```bash
cd backend
uv sync
cp .env.example .env     # then fill in your keys
uv run uvicorn app.api.main:app --reload --port 8000
```

Interactive API docs land at <http://localhost:8000/docs>.

See [backend/README.md](backend/README.md) for the full endpoint reference, the SSE event
contract, and the setup notes. [frontend/README.md](frontend/README.md) covers what the
client needs to talk to it.

## Conventions

- Each directory owns its own dependencies, config and README. There is no shared build
  or workspace tooling — run commands from inside `backend/` or `frontend/`.
- Secrets live in a git-ignored `.env` beside the code that reads them, never at the
  repository root.
- The backend's CORS allowlist (`CORS_ORIGINS`) must include the frontend's dev server
  origin, or the browser blocks every request.
