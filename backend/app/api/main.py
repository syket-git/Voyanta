"""FastAPI application entry point.

    uv run uvicorn app.api.main:app --reload --port 8000
"""

# Must stay the first import: app.config calls load_dotenv(), and LangChain reads
# LANGSMITH_* at import time. Import it after langchain and tracing silently stays off.
from app.config import settings  # isort:skip

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.agent import build_agent
from app.api.limiter import limiter
from app.api.routes import chat, feedback, threads
from app.auth import routes as auth_routes
from app.db import apply_schema
from app.logging_config import configure_logging, request_id_var
from app.observability import configure_tracing
from app.schemas import ErrorResponse

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_tracing()

    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Voyanta persists conversation threads in Postgres.\n"
            "Set DATABASE_URL in .env, or run scripts/cli_chat.py for an in-memory session."
        )

    # AsyncPostgresSaver requires all three connection kwargs; without them it fails in
    # ways that do not point back at the pool configuration.
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        max_size=20,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )

    await pool.open(wait=True, timeout=10)

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()  # idempotent
    await apply_schema(pool)

    app.state.pool = pool
    app.state.checkpointer = checkpointer
    app.state.agent = build_agent(checkpointer=checkpointer)

    logger.info("voyanta api ready", extra={"environment": settings.environment})

    try:
        yield
    finally:
        await pool.close()
        logger.info("voyanta api shut down")


app = FastAPI(
    title="Voyanta API",
    description="A LangGraph tour-planner agent over HTTP.",
    version=settings.app_version,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    # Also on request.state: the exception handler runs outside this middleware, by which
    # point the context var has already been reset.
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Never let a traceback reach the client — it leaks internals. Logs get the detail."""
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "unhandled error on %s %s",
        request.method,
        request.url.path,
        extra={"request_id": request_id},
    )
    body = ErrorResponse(error="Internal server error", request_id=request_id)
    return JSONResponse(
        status_code=500,
        content=body.model_dump(),
        headers={"X-Request-ID": request_id} if request_id else None,
    )


@app.get("/health", tags=["ops"])
async def health(request: Request):
    """Liveness plus a real database round-trip.

    A check that only returns 200 would report healthy while Postgres is down, which is
    the one situation it exists to catch.
    """
    db_ok = False

    try:
        async with request.app.state.pool.connection() as conn:
            await conn.execute("SELECT 1")
        db_ok = True
    except Exception as exc:  # noqa: BLE001 - the reason goes to the log, not the client
        logger.warning("health check: database unreachable: %s", exc)

    body = {
        "status": "ok" if db_ok else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "database": "ok" if db_ok else "unreachable",
        "tracing": settings.tracing_enabled,
    }

    return JSONResponse(status_code=200 if db_ok else 503, content=body)


app.include_router(auth_routes.router, prefix="/api", tags=["auth"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(threads.router, prefix="/api", tags=["threads"])
app.include_router(feedback.router, prefix="/api", tags=["feedback"])
