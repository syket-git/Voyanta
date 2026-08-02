"""Thread history — what lets the frontend restore a conversation after a page reload."""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ThreadHistory, serialize_message

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/threads/{thread_id}", response_model=ThreadHistory)
async def get_thread(thread_id: str, request: Request) -> ThreadHistory:
    """Return every message stored against a thread, oldest first."""
    agent = request.app.state.agent

    state = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    messages = (state.values or {}).get("messages", []) if state else []

    if not messages:
        raise HTTPException(status_code=404, detail=f"No thread found: {thread_id}")

    return ThreadHistory(
        thread_id=thread_id,
        messages=[serialize_message(m) for m in messages],
    )


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: str, request: Request) -> None:
    """Delete a thread's checkpoints. Idempotent — deleting a missing thread is fine."""
    checkpointer = request.app.state.checkpointer

    await checkpointer.adelete_thread(thread_id)
    logger.info("thread deleted", extra={"thread_id": thread_id})
