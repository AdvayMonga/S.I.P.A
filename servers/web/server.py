"""web MCP server: search the web for current/external info the model + vault don't have.

Backend-agnostic (see backend.py) — Tavily today. Only spawned when TAVILY_API_KEY is set."""

import json
import os

from mcp.server.fastmcp import FastMCP

from servers.web.backend import TavilyBackend, clean_markdown

mcp = FastMCP("web")
_backend = TavilyBackend(os.environ["TAVILY_API_KEY"])


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for current or external information. Returns JSON hits — each with title, url,
    and an extracted snippet, ranked best-first — ready to read, cite, and write into a note."""
    # Backend's relevance score is dropped: unused by any consumer, and a raw float misleads the
    # model (results are already ranked). See DECISIONS 2026-07-01.
    hits = _backend.search(query, max_results=max_results)
    return json.dumps([{"title": r.title, "url": r.url, "content": r.content} for r in hits])


@mcp.tool()
def web_fetch(url: str) -> str:
    """Fetch the full content of one web page by URL (extracted markdown). Returns JSON
    {url, content}, or an error field if the page couldn't be read."""
    results = _backend.fetch([url])
    if not results:
        return json.dumps({"url": url, "content": "", "error": "could not fetch"})
    # Shape the extracted page down to prose (drop image URLs + boilerplate whitespace) before it
    # enters the window — it's the largest single tool payload. See DECISIONS 2026-07-01.
    r = results[0]
    return json.dumps({"url": r.url, "content": clean_markdown(r.content)})


if __name__ == "__main__":
    mcp.run()
