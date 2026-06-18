"""Context assembly (VISION §5.9): per turn, pull the relevant slice of the durable stores into
the system prompt so the model just *knows* the user — no tool call needed. Pure-MCP; the loop
calls assemble_context once per turn. See design/context-assembly.md."""

import json
import re
from typing import Any, Protocol

TOTAL_BUDGET = 6000  # chars of injected context (~1500 tokens); never dump a whole store
PROFILE_SLICE = 2000  # profile gets its slot first (matches the memory store's PROFILE_CAP)
K_MEMORY = 5
K_VAULT = 5
# Relevance floors (bge-small cosine; baseline runs high, so ~0.55 only drops clear misses).
# A row missing its score is kept — gate only what we *know* is irrelevant. Tune as needed.
MEM_MIN_SCORE = 0.55
VAULT_MIN_SCORE = 0.55

# A greeting/ack/very-short turn has no real query → retrieval is noise (profile still loads).
_GREETING = re.compile(
    r"^(hi|hey|hello|yo|sup|thx|thanks|thank you|ok|okay|k|cool|nice|great|"
    r"got it|gm|gn|good morning|good night|good evening|bye|lol|np)\b[!. ]*$",
    re.IGNORECASE,
)


def is_trivial(message: str) -> bool:
    """True for greetings/acks/very-short turns — nothing meaningful to retrieve against."""
    m = message.strip()
    return len(m) <= 3 or bool(_GREETING.match(m))

_PREAMBLE = (
    "# Context (auto-retrieved; use if relevant, ignore if not; cite the source you use)"
)


class _Host(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]: ...


async def assemble_context(
    host: _Host, user_message: str, base_system: str, *, retrieve: bool = True
) -> str:
    """Build the per-turn system prompt: base + profile + top-k memory + top-k vault notes.

    One budget, allocated profile-first then the remainder split between memory and vault. Each
    source is best-effort: a failing or empty one is skipped. All empty → base unchanged.
    `retrieve=False` (trivial turns) keeps the profile but skips the query-driven retrieval.
    """
    profile = await _profile(host)
    sections = [profile]
    if retrieve:
        remainder = max(0, TOTAL_BUDGET - len(profile))
        each = remainder // 2
        sections.append(await _memory(host, user_message, each))
        sections.append(await _vault(host, user_message, each))

    sections = [s for s in sections if s]
    if not sections:
        return base_system
    block = "\n\n".join([_PREAMBLE, *sections])
    return f"{base_system}\n\n{block}"


async def _profile(host: _Host) -> str:
    text = await _safe(host, "memory_get_profile", {})
    if not text:
        return ""
    return "## About the user\n" + text[:PROFILE_SLICE]


async def _memory(host: _Host, query: str, budget: int) -> str:
    raw = await _safe(host, "memory_recall", {"query": query, "k": K_MEMORY})
    rows = [r for r in _loads(raw) if r.get("score", 1.0) >= MEM_MIN_SCORE]
    lines = [f"- (memory#{r['id']} · {r['kind']}) {r['content']}" for r in rows]
    body = _fit(lines, budget)
    return "## Possibly relevant memory\n" + body if body else ""


async def _vault(host: _Host, query: str, budget: int) -> str:
    raw = await _safe(host, "semantic_search", {"query": query, "k": K_VAULT})
    rows = [r for r in _loads(raw) if r.get("sim", 1.0) >= VAULT_MIN_SCORE]
    lines = []
    for r in rows:
        where = r["path"] + (f" › {r['heading']}" if r.get("heading") else "")
        lines.append(f"- (vault: {where}) {r['snippet']}")
    body = _fit(lines, budget)
    return "## Possibly relevant notes\n" + body if body else ""


async def _safe(host: _Host, tool: str, args: dict[str, Any]) -> str:
    """Call a tool; on error or non-zero is_error, degrade to empty so the turn never crashes."""
    try:
        text, is_error = await host.call_tool(tool, args)
        return "" if is_error else text
    except Exception:
        return ""


def _loads(raw: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _fit(lines: list[str], budget: int) -> str:
    """Take lines in rank order until the budget is full; truncate the line that overflows."""
    out: list[str] = []
    used = 0
    for line in lines:
        if used >= budget:
            break
        room = budget - used
        clipped = line if len(line) <= room else line[: room - 1] + "…"
        out.append(clipped)
        used += len(clipped) + 1  # +1 for the newline join
    return "\n".join(out)
