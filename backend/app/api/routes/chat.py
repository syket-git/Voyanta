"""Chat endpoints — one-shot JSON and SSE streaming."""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from app.agent import MODEL_NODE_NAME
from app.api.deps import require_turn, require_user
from app.api.limiter import limiter
from app.auth.sessions import AuthenticatedUser
from app.billing import Account, release_turn
from app.config import settings
from app.logging_config import run_id_var
from app.observability import build_run_config, new_run_id
from app.schemas import ChatRequest, ChatResponse, extract_tool_calls, message_text
from app.threads import repository

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _resolve_thread(pool, user: AuthenticatedUser, req: ChatRequest) -> str:
    """Return the thread this turn belongs to, creating it on the first message.

    Naming someone else's thread is rejected rather than silently redirected — otherwise
    a request could append turns to a stranger's conversation. The turn reserved by
    `require_turn` is handed back when that happens, since the model never ran.
    """
    try:
        if req.thread_id:
            if not await repository.owns_thread(pool, user.id, req.thread_id):
                raise HTTPException(status_code=404, detail="No thread found.")
            return req.thread_id

        thread = await repository.create_thread(
            pool, user.id, repository.title_from_message(req.message)
        )

        return thread.id
    except Exception:
        await release_turn(pool, user.id)
        raise


def _current_turn(messages: list[BaseMessage]) -> list[BaseMessage]:
    """The messages produced since the user's latest message.

    `ainvoke` returns the whole checkpointed thread, not just this turn, so reporting
    tool calls straight off it would replay every tool call the thread has ever made.
    """
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return messages[index:]
    return messages


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.chat_rate_limit)
async def chat(
    req: ChatRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
    account: Account = Depends(require_turn),
) -> ChatResponse:
    """Run one turn and return the complete reply."""
    pool = request.app.state.pool
    thread_id = await _resolve_thread(pool, user, req)
    run_id = new_run_id()
    run_id_var.set(run_id)

    config = build_run_config(thread_id, run_id, user_id=user.id)

    logger.info(
        "chat turn",
        extra={
            "thread_id": thread_id,
            "message_len": len(req.message),
            "turns_used": account.turns_used,
        },
    )

    try:
        result = await request.app.state.agent.ainvoke(
            {"messages": [{"role": "user", "content": req.message}]},
            config=config,
        )
    except Exception:
        await release_turn(pool, user.id)
        raise
    finally:
        await repository.touch_thread(pool, user.id, thread_id)

    messages = result.get("messages", [])
    reply = message_text(messages[-1]) if messages else ""

    tool_calls = []
    for message in _current_turn(messages):
        tool_calls.extend(extract_tool_calls(message))

    return ChatResponse(
        thread_id=thread_id,
        run_id=run_id,
        reply=reply,
        tool_calls=tool_calls,
    )


async def event_stream(
    request: Request,
    message: str,
    thread_id: str,
    run_id: str,
    user_id: str,
) -> AsyncIterator[str]:
    """Yield SSE frames for one turn.

    Event order: metadata -> (token | tool_start | tool_end)* -> done.
    On failure: error, then done.
    """
    run_id_var.set(run_id)
    agent = request.app.state.agent
    config = build_run_config(thread_id, run_id, user_id=user_id)

    yield _sse("metadata", {"thread_id": thread_id, "run_id": run_id})

    try:
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            if chunk["type"] == "messages":
                msg_chunk, meta = chunk["data"]

                # "messages" carries ToolMessages from the tools node as well as model
                # tokens, and would leak tokens from any future LLM-backed tool.
                if not isinstance(msg_chunk, AIMessageChunk):
                    continue

                if meta.get("langgraph_node") != MODEL_NODE_NAME:
                    continue

                text = message_text(msg_chunk)
                if text:
                    yield _sse("token", {"content": text})

            elif chunk["type"] == "updates":
                for update in (chunk["data"] or {}).values():
                    if not isinstance(update, dict):
                        continue
                    for m in update.get("messages") or []:
                        if isinstance(m, ToolMessage):
                            yield _sse(
                                "tool_end",
                                {"name": m.name, "preview": message_text(m)[:200]},
                            )
                            continue
                        for tc in getattr(m, "tool_calls", None) or []:
                            yield _sse(
                                "tool_start",
                                {"name": tc.get("name"), "args": tc.get("args") or {}},
                            )

    except Exception:
        # Must be caught inside the generator: raising after StreamingResponse has
        # started sends a truncated body under a 200 status and the client hangs.
        logger.exception("stream failed for thread %s", thread_id)
        await release_turn(request.app.state.pool, user_id)
        yield _sse("error", {"message": "Internal server error", "run_id": run_id})

    await repository.touch_thread(request.app.state.pool, user_id, thread_id)

    yield _sse("done", {"thread_id": thread_id, "run_id": run_id})


@router.post("/chat/stream")
@limiter.limit(settings.chat_rate_limit)
async def chat_stream(
    req: ChatRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_user),
    account: Account = Depends(require_turn),
) -> StreamingResponse:
    """Run one turn, streaming tokens to the browser as they are generated."""
    # Ownership is resolved before the response starts: once streaming begins the status
    # code is already 200 and a 404 can no longer be sent.
    thread_id = await _resolve_thread(request.app.state.pool, user, req)
    run_id = new_run_id()

    logger.info(
        "chat stream turn",
        extra={
            "thread_id": thread_id,
            "run_id": run_id,
            "turns_used": account.turns_used,
        },
    )

    return StreamingResponse(
        event_stream(request, req.message, thread_id, run_id, user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # stops nginx buffering the whole stream
        },
    )
