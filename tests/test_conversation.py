import asyncio
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock

from bot.conversation import (
    _ELIDED_RESULT,
    COMPACT_AFTER_TURNS,
    KEEP_RECENT_TURNS,
    Conversation,
    _demote_old_tool_results,
    _render,
    finalize_summary,
    maybe_compact,
)


class FakeProvider:
    """Returns a canned summary; records that it was called."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        self.calls += 1
        self.last_input = messages[0]["content"]
        return SimpleNamespace(content=[TextBlock(type="text", text="ROLLED SUMMARY")])

    def usage(self) -> dict:
        return {}


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _assistant(text: str) -> dict:
    return {"role": "assistant", "content": [TextBlock(type="text", text=text)]}


def _convo(turns: int) -> Conversation:
    msgs: list = []
    for i in range(turns):
        msgs.append(_user(f"q{i}"))
        msgs.append(_assistant(f"a{i}"))
    return Conversation(messages=msgs)


def test_no_compaction_under_threshold() -> None:
    convo = _convo(COMPACT_AFTER_TURNS)  # exactly at threshold → no-op
    provider = FakeProvider()
    ran = asyncio.run(maybe_compact(convo, provider))
    assert ran is False
    assert provider.calls == 0
    assert convo.summary == ""
    assert len(convo.messages) == COMPACT_AFTER_TURNS * 2


def test_compaction_folds_and_trims() -> None:
    convo = _convo(COMPACT_AFTER_TURNS + 3)  # over threshold
    provider = FakeProvider()
    ran = asyncio.run(maybe_compact(convo, provider))
    assert ran is True
    assert provider.calls == 1
    assert convo.summary == "ROLLED SUMMARY"
    # Exactly the most recent KEEP_RECENT_TURNS turns survive verbatim.
    assert len(convo.messages) == KEEP_RECENT_TURNS * 2
    assert convo.messages[0] == _user(f"q{COMPACT_AFTER_TURNS + 3 - KEEP_RECENT_TURNS}")
    # The kept window starts at a real user message (pairing-safe cut).
    assert convo.messages[0]["role"] == "user"
    assert isinstance(convo.messages[0]["content"], str)


def test_cut_never_lands_on_a_tool_result() -> None:
    # A turn that used a tool: user, assistant(tool_use), user(tool_result), assistant(text).
    convo = _convo(COMPACT_AFTER_TURNS)
    convo.messages.append(_user("use a tool please"))
    convo.messages.append({"role": "assistant", "content": [TextBlock(type="text", text="ok")]})
    convo.messages.append({"role": "user", "content": [{"type": "tool_result", "content": "42"}]})
    convo.messages.append(_assistant("done"))
    convo.messages.append(_user("and another"))
    convo.messages.append(_assistant("sure"))
    asyncio.run(maybe_compact(convo, FakeProvider()))
    # First kept message must be a real user turn, never an orphaned tool_result.
    first = convo.messages[0]
    assert first["role"] == "user" and isinstance(first["content"], str)


def test_finalize_summary_folds_remaining() -> None:
    convo = _convo(2)  # has messages but under the compaction threshold
    out = asyncio.run(finalize_summary(convo, FakeProvider()))
    assert out == "ROLLED SUMMARY"


def test_finalize_summary_no_messages_keeps_prior() -> None:
    convo = Conversation(summary="prior")  # nothing new this session
    provider = FakeProvider()
    out = asyncio.run(finalize_summary(convo, provider))
    assert out == "prior"
    assert provider.calls == 0  # no LLM call when there's nothing to fold


def test_demote_stubs_cold_results_keeps_recent() -> None:
    def tr(x: str) -> dict:
        block = {"type": "tool_result", "tool_use_id": x, "content": x}
        return {"role": "user", "content": [block]}

    msgs = [
        _user("q0"), _assistant("a0"), tr("t0"),  # cold turn → result stubbed
        _user("q1"), _assistant("a1"), tr("t1"),  # within last 2 turns → kept full
        _user("q2"), _assistant("a2"), tr("t2"),
    ]
    _demote_old_tool_results(msgs)  # KEEP_FULL_RESULTS_TURNS=2 → keep results from q1, q2
    assert msgs[2]["content"][0]["content"] == _ELIDED_RESULT  # t0 demoted
    assert msgs[2]["content"][0]["tool_use_id"] == "t0"  # structure/id preserved (pairing-safe)
    assert msgs[5]["content"][0]["content"] == "t1"  # recent kept full
    assert msgs[8]["content"][0]["content"] == "t2"


def test_demote_noop_when_few_turns() -> None:
    msgs = [_user("q0"), {"role": "user", "content": [{"type": "tool_result", "content": "keep"}]}]
    _demote_old_tool_results(msgs)  # only one real user turn → nothing is cold
    assert msgs[1]["content"][0]["content"] == "keep"


def test_render_flattens_tools() -> None:
    messages = [
        _user("hi"),
        {"role": "assistant", "content": [SimpleNamespace(name="vault_create_note", text=None)]},
        {"role": "user", "content": [{"type": "tool_result", "content": "created"}]},
        _assistant("done"),
    ]
    rendered = _render(messages)
    assert "user: hi" in rendered
    assert "tool_call: vault_create_note" in rendered
    assert "tool_result: created" in rendered
    assert "assistant: done" in rendered
