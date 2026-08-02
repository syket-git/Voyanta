"""The HTTP contract.

These models are the seam the React/Next frontend codes against — keep them stable, and
mirror any change in the TypeScript types on the other side.
"""

from typing import Any, Literal

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import BaseModel, Field

Role = Literal["user", "assistant", "tool", "system"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(
        default=None,
        max_length=255,
        description="Omit on the first turn; the server mints one and returns it.",
    )
    user_id: str | None = Field(default=None, max_length=255)


class ToolCallInfo(BaseModel):
    name: str
    args: dict[str, Any] = {}


class ChatResponse(BaseModel):
    thread_id: str
    run_id: str
    reply: str
    tool_calls: list[ToolCallInfo] = []


class MessageOut(BaseModel):
    id: str
    role: Role
    content: str
    tool_calls: list[ToolCallInfo] = []


class ThreadHistory(BaseModel):
    thread_id: str
    messages: list[MessageOut]


class FeedbackRequest(BaseModel):
    run_id: str = Field(max_length=255)
    score: Literal[0, 1] = Field(description="0 = thumbs down, 1 = thumbs up")
    comment: str | None = Field(default=None, max_length=1000)


class ErrorResponse(BaseModel):
    error: str
    request_id: str | None = None


def message_text(message: BaseMessage) -> str:
    """Flatten a message's content to a plain string.

    `content` is not always a string — with tool calls and multimodal models it can be a
    list of content blocks, which the frontend cannot render.
    """
    text = getattr(message, "text", None)

    if isinstance(text, str) and text:
        return text

    content = message.content

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)

    return str(content) if content else ""


def _role_of(message: BaseMessage) -> Role:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return "tool"
    if isinstance(message, SystemMessage):
        return "system"
    return "assistant"


def extract_tool_calls(message: BaseMessage) -> list[ToolCallInfo]:
    return [
        ToolCallInfo(name=tc.get("name", "unknown"), args=tc.get("args") or {})
        for tc in (getattr(message, "tool_calls", None) or [])
    ]


def serialize_message(message: BaseMessage) -> MessageOut:
    return MessageOut(
        id=str(getattr(message, "id", "") or ""),
        role=_role_of(message),
        content=message_text(message),
        tool_calls=extract_tool_calls(message),
    )
