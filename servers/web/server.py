"""web MCP server: search the web for current/external info the model + vault don't have.

Backend-agnostic (see backend.py) — Tavily today. Only spawned when TAVILY_API_KEY is set."""

import json
import os
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from servers.web.backend import TavilyBackend

mcp = FastMCP("web")
_backend = TavilyBackend(os.environ["TAVILY_API_KEY"])


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current or external information. Returns JSON hits — each with title, url,
    an extracted snippet, and score — ready to read, cite, and write into a note."""
    return json.dumps([asdict(r) for r in _backend.search(query, max_results=max_results)])


@mcp.tool()
def web_fetch(url: str) -> str:
    """Fetch the full content of one web page by URL (extracted markdown). Returns JSON
    {url, content}, or an error field if the page couldn't be read."""
    results = _backend.fetch([url])
    if not results:
        return json.dumps({"url": url, "content": "", "error": "could not fetch"})
    return json.dumps(asdict(results[0]))


if __name__ == "__main__":
    mcp.run()
