import asyncio
import json

from bot.context import (
    MEM_MIN_SCORE,
    TOTAL_BUDGET,
    VAULT_MIN_SCORE,
    assemble_context,
    is_trivial,
)

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


def _assemble(host: FakeHost, msg: str = "q", retrieve: bool = True) -> str:
    return asyncio.run(assemble_context(host, msg, BASE, retrieve=retrieve))


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


def test_retrieve_false_keeps_profile_skips_retrieval() -> None:
    host = FakeHost(
        {
            "memory_get_profile": ("[preference] terse", False),
            "memory_recall": (
                _mem([{"id": 1, "kind": "fact", "content": "x", "score": 0.9}]),
                False,
            ),
            "semantic_search": (
                _mem([{"path": "n.md", "snippet": "y", "sim": 0.9}]),
                False,
            ),
        }
    )
    out = _assemble(host, "hi", retrieve=False)
    assert "terse" in out  # profile (identity) still injected
    assert "Possibly relevant memory" not in out  # retrieval skipped entirely
    assert "Possibly relevant notes" not in out


def test_low_score_rows_are_gated_out() -> None:
    host = FakeHost(
        {
            "memory_get_profile": ("", False),
            "memory_recall": (
                _mem(
                    [
                        {"id": 1, "kind": "fact", "content": "keep me", "score": MEM_MIN_SCORE},
                        {
                            "id": 2,
                            "kind": "fact",
                            "content": "drop me",
                            "score": MEM_MIN_SCORE - 0.1,
                        },
                    ]
                ),
                False,
            ),
            "semantic_search": (
                _mem(
                    [
                        {"path": "a.md", "snippet": "keep note", "sim": VAULT_MIN_SCORE},
                        {"path": "b.md", "snippet": "drop note", "sim": VAULT_MIN_SCORE - 0.1},
                    ]
                ),
                False,
            ),
        }
    )
    out = _assemble(host)
    assert "keep me" in out and "drop me" not in out
    assert "keep note" in out and "drop note" not in out


def test_missing_score_is_kept() -> None:
    # Back-compat: a row without score/sim passes the gate (only known-irrelevant is dropped).
    host = FakeHost(
        {
            "memory_get_profile": ("", False),
            "memory_recall": (_mem([{"id": 1, "kind": "fact", "content": "no score"}]), False),
            "semantic_search": (_mem([]), False),
        }
    )
    assert "no score" in _assemble(host)


def test_is_trivial() -> None:
    for m in ("hi", "Hey!", "thanks", "ok", "good morning", "  yo  ", "k"):
        assert is_trivial(m), m
    for m in ("what's my flight", "remind me about Alice", "why?"):
        assert not is_trivial(m), m


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
