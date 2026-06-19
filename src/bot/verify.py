"""Adversarial claim-verification: before a research finding lands, independent skeptic sub-agents
try to REFUTE it via the web. Independence is the point — each skeptic sees only the claim, never
the reasoning that produced it, so it can't rubber-stamp. Reuses the sub-agent fan-out. Aggregation
is skeptical: 'supported' only if every skeptic confirms, 'refuted' if any does, else 'uncertain' —
err toward flagging, not asserting. See design/research.md."""

import re
from typing import Any

from .host import MCPHost
from .provider import ModelProvider
from .subagent import run_subagents

VOTERS = 2  # independent skeptics per claim — a panel, not a single second opinion

_SKEPTIC = (
    "You are a fact-checker whose job is to REFUTE one claim. Search the web for evidence that "
    "contradicts or fails to support it, and read the sources. Be skeptical: if no credible "
    "source confirms it, it is not supported. Give a one-sentence reason, then end with exactly "
    "this line:\nVERDICT: supported | refuted | uncertain"
)

VERIFY_TOOL: dict[str, Any] = {
    "name": "verify_claims",
    "description": (
        "Adversarially verify research findings before saving a deep-research note. Each claim is "
        "checked by independent skeptics that try to refute it via web search. Returns a verdict "
        "per claim: 'supported' (keep), 'refuted' (drop it), 'uncertain' (flag it). Pass the key "
        "factual claims you intend to write — short, self-contained, one fact each."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Self-contained factual claims to verify — one fact each.",
            }
        },
        "required": ["claims"],
    },
}

_VERDICT = re.compile(r"VERDICT:\s*(supported|refuted|uncertain)", re.IGNORECASE)


def _parse(reply: str) -> str:
    """Read the skeptic's final verdict line; missing/garbled → 'uncertain' (skeptical default)."""
    matches = _VERDICT.findall(reply)
    return matches[-1].lower() if matches else "uncertain"


def _aggregate(votes: list[str]) -> str:
    """Skeptical fuse: any refutation kills it; unanimous support passes it; otherwise uncertain."""
    if "refuted" in votes:
        return "refuted"
    if votes and all(v == "supported" for v in votes):
        return "supported"
    return "uncertain"


async def verify_claims(
    claims: list[str], provider: ModelProvider, host: MCPHost, voters: int = VOTERS
) -> list[dict[str, Any]]:
    """Refute each claim with `voters` independent skeptics; aggregate to a per-claim verdict."""
    if not claims:
        return []
    tasks: list[str] = []
    owner: list[int] = []
    for i, claim in enumerate(claims):
        for _ in range(voters):
            tasks.append(f"{_SKEPTIC}\n\nClaim to refute: {claim}")
            owner.append(i)
    replies = await run_subagents(tasks, provider, host)
    votes: list[list[str]] = [[] for _ in claims]
    for i, reply in zip(owner, replies, strict=True):
        votes[i].append(_parse(reply))
    return [
        {"claim": c, "verdict": _aggregate(v), "votes": v}
        for c, v in zip(claims, votes, strict=True)
    ]
