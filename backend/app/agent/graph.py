"""Builds the Voyanta LangGraph agent.

A plain ReAct loop — model, then tools, then model again until the model stops calling
tools. Reach for a hand-assembled StateGraph only if the planner later needs fixed stages
(research -> itinerary -> budget as nodes).
"""

import logging

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agent.prompts import SYSTEM_PROMPT
from app.config import settings
from app.tools import TOOLS

logger = logging.getLogger(__name__)

# The node `create_agent` runs the chat model in. The streaming endpoint filters on it to
# drop tokens produced by any other LLM call in the graph.
MODEL_NODE_NAME = "model"


def build_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        api_key=settings.openai_api_key,
        # Without a timeout a hung OpenAI call holds a worker open indefinitely.
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
    )


def build_agent(checkpointer: BaseCheckpointSaver | None = None):
    """Compile the agent.

    Args:
        checkpointer: The API passes AsyncPostgresSaver so threads survive restarts; the
            CLI script passes InMemorySaver so the agent can run without a database.
    """
    agent = create_agent(
        model=build_model(),
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )

    logger.info(
        "agent built model=%s tools=%s checkpointer=%s",
        settings.openai_model,
        [t.name for t in TOOLS],
        type(checkpointer).__name__ if checkpointer else "none",
    )

    return agent
