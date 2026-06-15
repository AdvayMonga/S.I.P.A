"""Context assembly (VISION §5.9): per turn, pull the relevant slice of the durable stores into
the system prompt so the model just *knows* the user — no tool call needed. Pure-MCP; the loop
calls assemble_context once per turn. See design/context-assembly.md."""

import json
from typing import Any, Protocol

TOTAL_BUDGET = 6000  # chars of injected context (~1500 tokens); never dump a whole store
PROFILE_SLICE = 2000  # profile gets its slot first (matches the memory store's PROFILE_CAP)
K_MEMORY = 5
K_VAULT = 5

_PREAMBLE = (
    "# Context (auto-retrieved; use if relevant, ignore if not; cite the source you use)"
)


class _Host(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]: ...


async def assemble_context(host: _Host, user_message: str, base_system: str) -> str:
    """Build the per-turn system prompt: base + profile + top-k memory + top-k vault notes.

    One budget, allocated profile-first then the remainder split between memory and vault. Each
    source is best-effort: a failing or empty one is skipped. All empty → base unchanged.
    """
    profile = await _profile(host)
    remainder = max(0, TOTAL_BUDGET - len(profile))
    each = remainder // 2
    memory = await _memory(host, user_message, each)
    vault = await _vault(host, user_message, each)

    sections = [s for s in (profile, memory, vault) if s]
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
    rows = _loads(raw)
    lines = [f"- (memory#{r['id']} · {r['kind']}) {r['content']}" for r in rows]
    body = _fit(lines, budget)
    return "## Possibly relevant memory\n" + body if body else ""


async def _vault(host: _Host, query: str, budget: int) -> str:
    raw = await _safe(host, "semantic_search", {"query": query, "k": K_VAULT})
    rows = _loads(raw)
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
