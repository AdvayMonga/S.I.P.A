"""Search backends behind a small protocol, so the web server is provider-agnostic — Tavily today,
SearXNG/Brave/etc. a one-class swap later (mirrors the Embedder seam)."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SearchResult:
    title: str
    url: str
    content: str  # an LLM-ready snippet/extract
    score: float


class SearchBackend(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class TavilyBackend:
    """Tavily search (purpose-built for agents: clean extracted content + citations). Client loads
    lazily on first call."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: Any = None

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if self._client is None:
            from tavily import TavilyClient

            self._client = TavilyClient(api_key=self._api_key)
        response = self._client.search(query=query, max_results=max_results, search_depth="basic")
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=float(r.get("score", 0.0)),
            )
            for r in response.get("results", [])
        ]
