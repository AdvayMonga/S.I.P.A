"""Conversation state + compaction — the within-session HANDOFF. Fold old turns into a rolling
summary when the window grows; the summary enriches retrieval and is injected so dropped context
survives. See design/conversation-memory.md."""

from dataclasses import dataclass, field
from typing import Any

from anthropic.types import TextBlock

from .provider import ModelProvider

COMPACT_AFTER_TURNS = 12  # real user turns before we compact
KEEP_RECENT_TURNS = 4  # turns kept verbatim after compaction

_SUMMARIZE_SYSTEM = (
    "You maintain a running summary of a conversation between a user and their personal assistant. "
    "Merge the prior summary with the new transcript into one concise summary. Capture durable "
    "facts about the user, decisions made, open threads/tasks, and stated preferences. Drop "
    "chit-chat. Write tight prose, no preamble."
)


@dataclass
class Conversation:
    """The live transcript plus a rolling summary of everything compacted out of it."""

    messages: list[Any] = field(default_factory=list)
    summary: str = ""


def _real_user_turns(messages: list[Any]) -> list[int]:
    """Indices of genuine user messages (string content) — safe cut points (never a tool_result)."""
    return [
        i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str)
    ]


async def maybe_compact(convo: Conversation, provider: ModelProvider) -> bool:
    """If grown past the threshold, fold older turns into the summary. Returns whether it ran."""
    turns = _real_user_turns(convo.messages)
    if len(turns) <= COMPACT_AFTER_TURNS:
        return False
    cut = turns[-KEEP_RECENT_TURNS]  # keep a clean window starting at a real user turn
    older, recent = convo.messages[:cut], convo.messages[cut:]
    convo.summary = await _summarize(provider, convo.summary, older)
    convo.messages = recent
    return True


async def _summarize(provider: ModelProvider, prior: str, messages: list[Any]) -> str:
    transcript = _render(messages)
    content = (f"Prior summary:\n{prior}\n\n" if prior else "") + f"New transcript:\n{transcript}"
    response = await provider.generate(
        system=_SUMMARIZE_SYSTEM, messages=[{"role": "user", "content": content}], tools=[]
    )
    return "".join(b.text for b in response.content if isinstance(b, TextBlock)).strip()


def _render(messages: list[Any]) -> str:
    """Flatten messages to text for summarization; tool calls/results reduce to brief markers."""
    lines: list[str] = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            lines.append(f"{m['role']}: {content}")
            continue
        for block in content:
            text = getattr(block, "text", None)
            name = getattr(block, "name", None)
            if isinstance(block, dict) and block.get("type") == "tool_result":
                lines.append(f"tool_result: {str(block.get('content', ''))[:200]}")
            elif text:
                lines.append(f"{m['role']}: {text}")
            elif name:
                lines.append(f"tool_call: {name}")
    return "\n".join(lines)
