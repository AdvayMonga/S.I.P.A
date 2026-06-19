import asyncio
from typing import Any, cast

import bot.verify as verify
from bot.verify import _aggregate, _parse, verify_claims

_NONE: Any = cast("Any", None)  # run_subagents is monkeypatched, so provider/host go unused


def test_parse_reads_final_verdict() -> None:
    assert _parse("looks solid.\nVERDICT: supported") == "supported"
    assert _parse("no source backs this.\nVERDICT: refuted") == "refuted"
    # takes the last verdict line if the model emits more than one
    assert _parse("VERDICT: uncertain\n...\nVERDICT: supported") == "supported"


def test_parse_missing_defaults_uncertain() -> None:
    assert _parse("I couldn't decide.") == "uncertain"
    assert _parse("") == "uncertain"


def test_aggregate_is_skeptical() -> None:
    assert _aggregate(["supported", "supported"]) == "supported"  # unanimous → keep
    assert _aggregate(["supported", "refuted"]) == "refuted"  # any refutation → kill
    assert _aggregate(["supported", "uncertain"]) == "uncertain"  # not unanimous → flag
    assert _aggregate(["refuted", "refuted"]) == "refuted"
    assert _aggregate([]) == "uncertain"


def test_verify_claims_empty_no_fanout(monkeypatch) -> None:
    called = False

    async def fake_run_subagents(tasks, provider, host):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(verify, "run_subagents", fake_run_subagents)
    out = asyncio.run(verify_claims([], provider=_NONE, host=_NONE))
    assert out == []
    assert called is False


def test_verify_claims_aggregates_per_claim(monkeypatch) -> None:
    # 2 claims x 2 voters = 4 skeptic tasks, in claim-major order.
    replies = [
        "ok\nVERDICT: supported",  # claim 0, voter 0
        "ok\nVERDICT: supported",  # claim 0, voter 1  -> supported
        "ok\nVERDICT: supported",  # claim 1, voter 0
        "no\nVERDICT: refuted",  # claim 1, voter 1   -> refuted
    ]
    captured: dict = {}

    async def fake_run_subagents(tasks, provider, host):
        captured["tasks"] = tasks
        return replies

    monkeypatch.setattr(verify, "run_subagents", fake_run_subagents)
    claims = ["earth is round", "moon is cheese"]
    out = asyncio.run(verify_claims(claims, provider=_NONE, host=_NONE))

    assert len(captured["tasks"]) == 4  # 2 claims x VOTERS(2)
    assert out[0]["claim"] == "earth is round"
    assert out[0]["verdict"] == "supported"
    assert out[1]["verdict"] == "refuted"
    assert out[1]["votes"] == ["supported", "refuted"]
