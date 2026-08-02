"""Thread listing and history — what backs the sidebar and survives a page reload."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_user
from app.auth.sessions import AuthenticatedUser
from app.schemas import (
    RenameThreadRequest,
    ThreadHistory,
    ThreadSummary,
    serialize_message,
)
from app.threads import repository

logger = logging.getLogger(__name__)
router = APIRouter()

# Someone else's thread is reported as missing rather than forbidden, so thread ids
# cannot be probed for existence.
NOT_FOUND = "No thread found."


@router.get("/threads", response_model=list[ThreadSummary])
async def list_threads(
    request: Request, user: AuthenticatedUser = Depends(require_user)
) -> list[ThreadSummary]:
    """The caller's threads, most recently used first."""
    return await repository.list_threads(request.app.state.pool, user.id)


@router.get("/threads/{thread_id}", response_model=ThreadHistory)
async def get_thread(
    thread_id: str, request: Request, user: AuthenticatedUser = Depends(require_user)
) -> ThreadHistory:
    """Return every message stored against a thread, oldest first."""
    pool = request.app.state.pool

    if not await repository.owns_thread(pool, user.id, thread_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)

    state = await request.app.state.agent.aget_state(
        {"configurable": {"thread_id": thread_id}}
    )
    messages = (state.values or {}).get("messages", []) if state else []

    return ThreadHistory(
        thread_id=thread_id,
        messages=[serialize_message(m) for m in messages],
    )


@router.patch("/threads/{thread_id}", response_model=ThreadSummary)
async def rename_thread(
    thread_id: str,
    req: RenameThreadRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
) -> ThreadSummary:
    thread = await repository.rename_thread(
        request.app.state.pool, user.id, thread_id, req.title.strip()
    )

    if thread is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)

    return thread


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str, request: Request, user: AuthenticatedUser = Depends(require_user)
) -> None:
    """Delete a thread and the messages checkpointed against it."""
    if not await repository.delete_thread(request.app.state.pool, user.id, thread_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)

    await request.app.state.checkpointer.adelete_thread(thread_id)
    logger.info("thread deleted", extra={"thread_id": thread_id})
