"""LangSmith wiring.

Tracing itself needs no code — LangChain picks up LANGSMITH_* from the environment. What
this module adds is what makes traces useful: every run is tagged with the thread, the
environment and the app version, carries a run_id we chose ourselves, and can receive
user feedback afterwards.
"""

import logging
import os
import uuid
from functools import lru_cache

from langsmith import Client

from app.config import settings

logger = logging.getLogger(__name__)


def configure_tracing() -> None:
    """Reconcile the tracing settings with the environment LangChain reads at startup."""
    if settings.tracing_enabled:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        logger.info(
            "langsmith tracing enabled (project=%s)", settings.langsmith_project
        )
    else:
        os.environ["LANGSMITH_TRACING"] = "false"
        logger.warning(
            "langsmith tracing disabled — set LANGSMITH_API_KEY and "
            "LANGSMITH_TRACING=true to enable it"
        )


def new_run_id() -> str:
    """Generate the run id up front.

    Pre-generating matters for streaming: a post-hoc run collector would only hand us an
    id after the response is flushed, too late to tell the client which trace produced it.
    """
    return str(uuid.uuid4())


def build_run_config(
    thread_id: str,
    run_id: str,
    user_id: str | None = None,
) -> dict:
    """Assemble a run's config, so every endpoint tags identically.

    `thread_id` appears in metadata as well as configurable on purpose: LangSmith groups
    runs into conversation Threads by the metadata key.
    """
    return {
        "configurable": {"thread_id": thread_id},
        "run_id": run_id,
        "run_name": "voyanta_chat",
        "tags": ["voyanta", settings.environment],
        "metadata": {
            "thread_id": thread_id,
            "user_id": user_id,
            "app_version": settings.app_version,
            "model": settings.openai_model,
            "environment": settings.environment,
        },
        "recursion_limit": settings.recursion_limit,
    }


@lru_cache(maxsize=1)
def get_langsmith_client() -> Client | None:
    if not settings.langsmith_api_key:
        return None
    return Client(api_key=settings.langsmith_api_key)


@lru_cache(maxsize=1)
def _project_session_id() -> str | None:
    """Resolve the tracing project's id, which LangSmith calls the feedback session_id.

    Submitting feedback without it is deprecated.
    """
    client = get_langsmith_client()

    if client is None:
        return None

    try:
        project = client.read_project(project_name=settings.langsmith_project)
        return str(project.id)
    except Exception as exc:  # noqa: BLE001 - feedback still works without it
        logger.warning(
            "could not resolve langsmith project %r: %s",
            settings.langsmith_project,
            exc,
        )
        return None


def submit_feedback(
    run_id: str,
    score: int,
    comment: str | None = None,
    key: str = "user_score",
) -> None:
    """Record a thumbs up/down against a run.

    Runs in a FastAPI BackgroundTask, so a slow or failing LangSmith call must never
    propagate — the user's message already succeeded.
    """
    client = get_langsmith_client()

    if client is None:
        logger.warning("feedback dropped for run %s: no LANGSMITH_API_KEY", run_id)
        return

    try:
        # run_id is the id of the *root* run, so it doubles as the trace_id.
        client.create_feedback(
            run_id,
            key=key,
            score=score,
            comment=comment,
            trace_id=run_id,
            session_id=_project_session_id(),
        )
        logger.info("feedback recorded run_id=%s score=%s", run_id, score)
    except Exception as exc:  # noqa: BLE001 - background task must not raise
        logger.warning("failed to record feedback for run %s: %s", run_id, exc)
