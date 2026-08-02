"""Web search via Tavily.

The client is built lazily: constructing it at import time turns a missing API key into a
traceback at server startup rather than a recoverable message at call time.
"""

import logging
from functools import lru_cache

from langchain.tools import tool
from tavily import TavilyClient

from app.config import settings

logger = logging.getLogger(__name__)

MAX_RESULTS = 5


@lru_cache(maxsize=1)
def _client() -> TavilyClient:
    return TavilyClient(api_key=settings.tavily_api_key)


@tool("web_search")
def web_search(query: str) -> str:
    """Search the web for current travel information.

    Use this for anything that is not live flight status: attractions and things to do,
    sample itineraries, visa and entry requirements, weather by season, hotel and flight
    price estimates, local transport, food, costs, customs, and safety advisories.

    Returns up to 5 results, each with a title, URL and content snippet. Cite the URLs
    when you state a fact drawn from them.

    Args:
        query: A specific search query. Prefer "visa requirements for Bangladeshi
            citizens visiting Japan" over "Japan visa".
    """
    if not settings.tavily_api_key:
        return (
            "Web search error: TAVILY_API_KEY is missing.\n"
            "Add TAVILY_API_KEY=your_api_key_here to your .env file."
        )

    try:
        response = _client().search(query=query, max_results=MAX_RESULTS)
    except Exception as exc:  # noqa: BLE001 - tool errors must reach the model as text
        logger.warning("tavily search failed for %r: %s", query, exc)
        return f"Web search failed: {exc}. Try rephrasing the query."

    results = response.get("results", [])

    if not results:
        return f"No web results found for '{query}'. Try a broader or rephrased query."

    blocks = [
        "Result {n}:\nTitle: {title}\nURL: {url}\nSnippet: {snippet}\n".format(
            n=i + 1,
            title=item.get("title", "unknown"),
            url=item.get("url", "unknown"),
            snippet=item.get("content", "unknown"),
        )
        for i, item in enumerate(results)
    ]

    return "\n".join(blocks)
