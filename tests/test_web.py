from typing import Any

from servers.web.backend import SearchResult, TavilyBackend


class FakeTavily:
    """Stands in for TavilyClient — returns a canned Tavily response shape, no network."""

    def __init__(self, results: list[dict]) -> None:
        self._results = results
        self.last_kwargs: dict[str, Any] = {}

    def search(self, **kwargs: Any) -> dict:
        self.last_kwargs = kwargs
        return {"query": kwargs.get("query"), "results": self._results}


def _backend(results: list[dict]) -> TavilyBackend:
    b = TavilyBackend("tvly-test")
    b._client = FakeTavily(results)  # inject; skips the lazy real-client construction
    return b


def test_normalizes_results() -> None:
    b = _backend(
        [{"title": "T", "url": "https://x", "content": "snippet", "score": 0.91, "extra": "skip"}]
    )
    out = b.search("python asyncio", max_results=3)
    assert out == [SearchResult(title="T", url="https://x", content="snippet", score=0.91)]
    assert b._client.last_kwargs["query"] == "python asyncio"  # type: ignore[attr-defined]
    assert b._client.last_kwargs["max_results"] == 3  # type: ignore[attr-defined]


def test_missing_fields_default() -> None:
    out = _backend([{"url": "https://y"}]).search("q")
    assert out == [SearchResult(title="", url="https://y", content="", score=0.0)]


def test_empty_results() -> None:
    assert _backend([]).search("nothing here") == []
