from typing import Any

from servers.web.backend import FetchResult, SearchResult, TavilyBackend


class FakeTavily:
    """Stands in for TavilyClient — returns canned Tavily response shapes, no network."""

    def __init__(self, results: list[dict], extracts: list[dict] | None = None) -> None:
        self._results = results
        self._extracts = extracts or []
        self.last_kwargs: dict[str, Any] = {}

    def search(self, **kwargs: Any) -> dict:
        self.last_kwargs = kwargs
        return {"query": kwargs.get("query"), "results": self._results}

    def extract(self, **kwargs: Any) -> dict:
        self.last_kwargs = kwargs
        return {"results": self._extracts, "failed_results": []}


def _backend(
    results: list[dict] | None = None, extracts: list[dict] | None = None
) -> TavilyBackend:
    b = TavilyBackend("tvly-test")
    b._client = FakeTavily(results or [], extracts)  # inject; skips real-client construction
    return b


def test_normalizes_results() -> None:
    b = _backend([{"title": "T", "url": "https://x", "content": "snippet", "score": 0.91}])
    out = b.search("python asyncio", max_results=3)
    assert out == [SearchResult(title="T", url="https://x", content="snippet", score=0.91)]
    assert b._client.last_kwargs["query"] == "python asyncio"  # type: ignore[attr-defined]
    assert b._client.last_kwargs["max_results"] == 3  # type: ignore[attr-defined]


def test_missing_fields_default() -> None:
    out = _backend([{"url": "https://y"}]).search("q")
    assert out == [SearchResult(title="", url="https://y", content="", score=0.0)]


def test_empty_results() -> None:
    assert _backend([]).search("nothing here") == []


def test_fetch_normalizes() -> None:
    b = _backend(extracts=[{"url": "https://x", "raw_content": "# Page\nbody"}])
    out = b.fetch(["https://x"])
    assert out == [FetchResult(url="https://x", content="# Page\nbody")]
    assert b._client.last_kwargs["urls"] == ["https://x"]  # type: ignore[attr-defined]


def test_fetch_empty() -> None:
    assert _backend().fetch(["https://nope"]) == []
