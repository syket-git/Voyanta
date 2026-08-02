"""The tool belt bound to the agent."""

from app.tools.flight_tool import search_flights
from app.tools.tavily_tool import web_search

TOOLS = [search_flights, web_search]

__all__ = ["TOOLS", "search_flights", "web_search"]
