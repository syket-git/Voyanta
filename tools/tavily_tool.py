from tavily import TavilyClient
from dotenv import load_dotenv
import os

load_dotenv()

client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def tavily_search(query: str):
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY is not set in the environment variables.")

    response = client.search(query=query, max_results=5)

    results = []

    for i, item in enumerate(response.get("results", [])):
        result = {
            "title": item.get("title", "unknown"),
            "url": item.get("url", "unknown"),
            "snippet": item.get("content", "unknown"),
        }
        results.append(
            f"Result {i + 1}:\nTitle: {result['title']}\nURL: {result['url']}\nSnippet: {result['snippet']}\n"
        )

    return "\n".join(results)
