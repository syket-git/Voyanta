"""A terminal REPL for the agent.

Uses InMemorySaver rather than Postgres on purpose: when something misbehaves, this tells
you whether the problem is the agent or the database, without needing both to be healthy.

    uv run python scripts/cli_chat.py
"""

import asyncio
import logging
import sys
import uuid

from langchain_core.messages import AIMessageChunk
from langgraph.checkpoint.memory import InMemorySaver

from app.agent import MODEL_NODE_NAME, build_agent
from app.config import settings
from app.observability import build_run_config, configure_tracing, new_run_id
from app.schemas import message_text

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


async def main() -> None:
    configure_tracing()

    agent = build_agent(checkpointer=InMemorySaver())
    thread_id = str(uuid.uuid4())

    print("Voyanta CLI — type your travel request. Ctrl-C or 'exit' to quit.")
    print(f"model={settings.openai_model}  thread={thread_id}")
    if settings.tracing_enabled:
        print(f"tracing -> LangSmith project '{settings.langsmith_project}'")
    print()

    while True:
        try:
            message = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not message:
            continue
        if message.lower() in {"exit", "quit"}:
            return

        run_id = new_run_id()
        config = build_run_config(thread_id, run_id)

        print("\nvoyanta > ", end="", flush=True)

        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            stream_mode=["messages", "updates"],
            version="v2",
        ):
            if chunk["type"] == "messages":
                msg_chunk, meta = chunk["data"]
                if not isinstance(msg_chunk, AIMessageChunk):
                    continue
                if meta.get("langgraph_node") != MODEL_NODE_NAME:
                    continue
                if text := message_text(msg_chunk):
                    print(text, end="", flush=True)

            elif chunk["type"] == "updates":
                for update in (chunk["data"] or {}).values():
                    if not isinstance(update, dict):
                        continue
                    for m in update.get("messages") or []:
                        for tc in getattr(m, "tool_calls", None) or []:
                            print(f"\n  [tool] {tc['name']}({tc['args']})", flush=True)

        print(f"\n\n  run_id={run_id}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
