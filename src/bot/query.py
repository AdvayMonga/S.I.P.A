"""Query transformation (BACKLOG §51b): rewrite a context-dependent follow-up into a standalone
retrieval query before searching, so "what about the second one?" resolves its referents from
recent turns instead of embedding vague literal words. Used only for retrieval, never shown to
the user — a bad rewrite degrades recall slightly, it never corrupts the conversation."""

import re
from typing import Any

from anthropic.types import TextBlock

from .conversation import Conversation
from .provider import ModelProvider

RECENT_TURNS = 4  # recent text turns the rewriter sees to resolve referents
SUMMARY_SLICE = 800  # chars of rolling summary fed to the rewriter
SHORT_TURN_WORDS = 6  # a message this short is ambiguous → resolve it even without a pronoun

# Referential markers — pronouns/deixis whose referent lives in prior turns. A message with one of
# these (or that's very short) is context-dependent → worth resolving; otherwise it stands alone.
_REFERENTIAL = re.compile(
    r"\b(it|its|that|those|these|this|them|they|their|he|she|him|her|his|"
    r"the (first|second|third|last|next|previous|other|same|former|latter) one|"
    r"the (former|latter)|above|below|earlier)\b",
    re.IGNORECASE,
)

_REWRITE_SYSTEM = (
    "Rewrite the user's latest message into a standalone search query for retrieving relevant "
    "notes and memories. Resolve pronouns and references ('the second one', 'that', 'it') using "
    "the conversation so far. Keep it short and keyword-rich. If the message is already "
    "self-contained, return it unchanged. Output ONLY the query — no preamble, no quotes."
)


def _needs_rewrite(message: str, convo: Conversation) -> bool:
    """Only spend a rewrite call when there's prior context AND the message looks dependent."""
    has_history = bool(convo.summary) or any(
        m["role"] == "user" and isinstance(m["content"], str) for m in convo.messages
    )
    if not has_history:
        return False
    return len(message.split()) <= SHORT_TURN_WORDS or bool(_REFERENTIAL.search(message))


async def rewrite_query(provider: ModelProvider, convo: Conversation, user_message: str) -> str:
    """Resolve a follow-up into a standalone retrieval query; raw message if not warranted/fails."""
    if not _needs_rewrite(user_message, convo):
        return user_message
    content = f"{_recent(convo)}\n\nLatest message: {user_message}\n\nStandalone query:"
    try:
        response = await provider.generate(
            system=_REWRITE_SYSTEM, messages=[{"role": "user", "content": content}], tools=[]
        )
        text = "".join(b.text for b in response.content if isinstance(b, TextBlock)).strip()
        return text or user_message
    except Exception:
        return user_message


def _recent(convo: Conversation) -> str:
    """Rolling summary + the last few text turns — the referents the rewriter resolves against."""
    parts: list[str] = []
    if convo.summary:
        parts.append(f"Summary so far: {convo.summary[-SUMMARY_SLICE:]}")
    lines: list[str] = []
    for m in convo.messages:
        content: Any = m["content"]
        text = content if isinstance(content, str) else "".join(
            getattr(b, "text", "") for b in content
        )
        if text:
            lines.append(f"{m['role']}: {text}")
    parts.extend(lines[-RECENT_TURNS * 2 :])
    return "\n".join(parts)
