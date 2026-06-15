import asyncio
import json

from bot.context import TOTAL_BUDGET, assemble_context

BASE = "BASE SYSTEM"


class FakeHost:
    """Canned MCP responses keyed by tool name. raises=True simulates a server failure."""

    def __init__(self, responses: dict[str, tuple[str, bool]], raises: set[str] | None = None):
        self._responses = responses
        self._raises = raises or set()

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        if name in self._raises:
            raise RuntimeError("server down")
        return self._responses.get(name, ("", False))


def _assemble(host: FakeHost, msg: str = "q") -> str:
    return asyncio.run(assemble_context(host, msg, BASE))


def _mem(rows: list[dict]) -> str:
    return json.dumps(rows)


def test_all_sources_present_with_provenance() -> None:
    host = FakeHost(
        {
            "memory_get_profile": ("[preference] likes terse replies", False),
            "memory_recall": (
                _mem([{"id": 12, "kind": "fact", "content": "flight is June 20"}]),
                False,
            ),
            "semantic_search": (
                _mem([{"path": "Summer.md", "heading": "Goals", "snippet": "ship the daemon"}]),
                False,
            ),
        }
    )
    out = _assemble(host, "what's my plan")
    assert out.startswith(BASE)
    assert "## About the user" in out and "likes terse replies" in out
    assert "(memory#12 · fact) flight is June 20" in out
    assert "(vault: Summer.md › Goals) ship the daemon" in out
    assert "cite the source" in out  # preamble present


def test_empty_stores_return_base_unchanged() -> None:
    host = FakeHost(
        {
            "memory_get_profile": ("", False),
            "memory_recall": (_mem([]), False),
            "semantic_search": (_mem([]), False),
        }
    )
    assert _assemble(host, "hi") == BASE


def test_failing_retrieval_is_skipped_not_fatal() -> None:
    host = FakeHost(
        {
            "memory_get_profile": ("[entity] Alice = cofounder", False),
            "semantic_search": (_mem([{"path": "n.md", "heading": "", "snippet": "x"}]), False),
        },
        raises={"memory_recall"},  # memory server explodes
    )
    out = _assemble(host)
    assert "Alice = cofounder" in out  # profile survived
    assert "Possibly relevant memory" not in out  # bad source skipped
    assert "(vault: n.md) x" in out  # no heading → no separator


def test_is_error_result_is_skipped() -> None:
    host = FakeHost(
        {
            "memory_get_profile": ("error text", True),  # is_error → treated as empty
            "memory_recall": (_mem([]), False),
            "semantic_search": (_mem([]), False),
        }
    )
    assert _assemble(host, "hi") == BASE


def test_budget_truncates() -> None:
    big = [{"id": i, "kind": "fact", "content": "x" * 500} for i in range(20)]
    host = FakeHost(
        {
            "memory_get_profile": ("", False),
            "memory_recall": (_mem(big), False),
            "semantic_search": (_mem([]), False),
        }
    )
    out = _assemble(host)
    injected = out[len(BASE) :]  # block excludes base
    assert len(injected) <= TOTAL_BUDGET + 200  # +headers/preamble slack
    assert "…" in out  # the overflowing line was clipped
