"""Web backends behind a small protocol, so the web server is provider-agnostic — Tavily today,
SearXNG/Brave/etc. a one-class swap later (mirrors the Embedder seam)."""

import re
from dataclasses import dataclass
from typing import Any, Protocol


def clean_markdown(text: str) -> str:
    """Trim boilerplate from extracted page markdown without touching prose: image embeds collapse
    to their alt text (the URL is unusable to the model), trailing whitespace goes, blank-line runs
    collapse. Inline link targets are deliberately kept — deep research follows them to new sources.
    Pure + idempotent, so shaped fetches don't bust the message-prefix cache."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)  # ![alt](url) -> alt
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


@dataclass
class SearchResult:
    title: str
    url: str
    content: str  # an LLM-ready snippet/extract
    score: float


@dataclass
class FetchResult:
    url: str
    content: str  # the full extracted page (markdown)


class WebBackend(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]: ...
    def fetch(self, urls: list[str]) -> list[FetchResult]: ...


class TavilyBackend:
    """Tavily — agent-friendly search + extract. Client loads lazily on first call."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            from tavily import TavilyClient

            self._client = TavilyClient(api_key=self._api_key)
        return self._client

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        response = self._ensure().search(
            query=query, max_results=max_results, search_depth="basic"
        )
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=float(r.get("score", 0.0)),
            )
            for r in response.get("results", [])
        ]

    def fetch(self, urls: list[str]) -> list[FetchResult]:
        response = self._ensure().extract(urls=urls)
        return [
            FetchResult(url=r.get("url", ""), content=r.get("raw_content", ""))
            for r in response.get("results", [])
        ]
