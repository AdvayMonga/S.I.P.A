"""Stateless agent loop: model call -> tool calls -> repeat until a final answer."""

import asyncio
import json
import logging
from typing import Any, cast

from anthropic.types import TextBlock, ToolUseBlock

from .context import assemble_context, is_trivial
from .conversation import Conversation, maybe_compact
from .daemon import Ask
from .host import MCPHost
from .provider import ModelProvider
from .query import rewrite_query
from .subagent import DELEGATE_TOOL, run_subagents
from .verify import VERIFY_TOOL, verify_claims

_log = logging.getLogger("sipa.loop")

WARN_ITERATIONS = 15  # soft: log and keep going — don't interrupt a legitimately long task
MAX_ITERATIONS = 40  # hard backstop: stop a runaway turn (tool calls that never converge)

# Bound a pathologically large tool result to head+tail so one blob can't flood the window (hurting
# both attention and the context budget). Generous — only true monsters trip it; normal outputs and
# typical web_fetch pages pass through. Deterministic + idempotent so it won't bust the cache.
TOOL_RESULT_CHAR_CAP = 48_000  # ~12k tokens
TOOL_RESULT_HEAD = 36_000
TOOL_RESULT_TAIL = 8_000


def _cap(content: Any) -> Any:
    """Trim an oversized tool result to head+tail with an elision marker. Strings only; image/
    multimodal lists pass through untouched. Pure function of its input (no clock/randomness)."""
    if not isinstance(content, str) or len(content) <= TOOL_RESULT_CHAR_CAP:
        return content
    elided = len(content) - TOOL_RESULT_HEAD - TOOL_RESULT_TAIL
    return (
        f"{content[:TOOL_RESULT_HEAD]}"
        f"\n\n[… {elided} characters elided to save context …]\n\n"
        f"{content[-TOOL_RESULT_TAIL:]}"
    )

# Tools whose effects are irreversible/external — gated behind user approval. Reversible tools
# (vault writes auto-commit to git, reads, search) run freely. `run_shell` is the first member.
APPROVAL_REQUIRED: set[str] = {"run_shell"}


def _signature(name: str, args: dict[str, Any]) -> str:
    """A stable key for the allowlist — the shell command itself, else the tool name."""
    return args["command"] if name == "run_shell" and "command" in args else name


class Approver:
    """Permission policy for irreversible/external tools (Claude-Code-style). `mode='trust'` runs
    without asking; otherwise asks per action, with an in-session allowlist ("always") so you're not
    re-prompted for the same command. Unattended turns (ask is None) are always denied."""

    def __init__(self, mode: str = "ask") -> None:
        self._mode = mode  # "ask" | "trust"
        self._allow: set[str] = set()  # signatures pre-approved this session

    async def approve(self, name: str, args: dict[str, Any], ask: Ask | None) -> bool:
        if ask is None:  # unattended-block — never on a timer or in a background agent
            _log.info("denied %s — no interactive session to approve", name)
            return False
        sig = _signature(name, args)
        if self._mode == "trust" or sig in self._allow:
            return True
        question = f"Approve `{name}`: {sig[:200]}  [y]es · [a]lways · [N]o"
        answer = (await ask(question)).strip().lower()
        if answer in {"a", "always"}:
            self._allow.add(sig)
            return True
        return answer in {"y", "yes"}

SYSTEM = (
    "You are S.I.P.A., a personal assistant with access to an Obsidian vault. "
    "When the user asks you to save, note, or write something down, create a note "
    "with the vault tools. Choose a sensible Markdown path and title. "
    "Answer directly and concisely. "
    "After taking actions (edits, file changes, commands), briefly report what you did — one short "
    "line per action — so the user can see it and undo it if needed."
    "\n\n# Research\n"
    "Two depths. SHALLOW (a single fact or quick lookup): answer inline with at most one "
    "web_search, no note. DEEP (multi-source, multi-entity, comparison, or anything worth keeping):"
    " run the flow below and save a note. Explicit wins — 'deep research' / 'save this' force deep,"
    "'just quickly check' forces shallow; borderline → answer inline, then offer to save. "
    "If the topic is vague (scope/region/use-case), ask one clarifying question first.\n"
    "Flow: (1) Decompose the request into sub-questions along its dominant axis (per entity / "
    "attribute / theme) and search each separately — never one broad query. (2) Iterate — read, "
    "web_fetch the full page for anything you'll state as a finding (don't cite search snippets), "
    "spot gaps, search again, until every sub-question is covered. (3) Ground every finding in a "
    "source you actually fetched with an inline [^n] citation; drop or flag what isn't grounded. "
    "(4) Before saving, call verify_claims on your key factual claims — drop the ones it returns "
    "'refuted', mark 'uncertain' ones as unverified in the note, keep 'supported'.\n"
    "Save to Research/<topic>.md: frontmatter (created, type: research, topic), a ## Summary (2–4 "
    "sentences), a body organized by the dominant axis (## per section, inline [^n] cites), a "
    "## Sources footer (footnoted fetched URLs), and a ## Related footer of [[wikilinks]] resolved "
    "via vault_resolve_link. Default one note sectioned by entity; split into linked per-entity "
    "notes only when asked or when entities are clearly distinct subjects. Update an existing note "
    "on the topic rather than duplicating it."
)


async def run_turn(
    convo: Conversation,
    user_message: str,
    provider: ModelProvider,
    host: MCPHost,
    *,
    allow_delegate: bool = False,
    ask: Ask | None = None,
    approver: "Approver | None" = None,
    roster: str = "",
) -> str:
    """Run one user turn to completion, mutating `convo` in place. `allow_delegate` offers the
    `delegate` fan-out tool — only top-level turns set it, so sub-agents can't recurse. `ask` asks
    the user for approval mid-flight (None = unattended → approval-gated tools are denied)."""
    await maybe_compact(convo, provider)  # bound the window before we build the turn
    # Resolve context-dependent follow-ups into a standalone retrieval query (skip on trivial turns
    # — they don't retrieve anyway). See query.py.
    trivial = is_trivial(user_message)
    query = user_message if trivial else await rewrite_query(provider, convo, user_message)
    # Assemble context once on the query; reuse it across this turn's tool-use iterations.
    # Greetings/acks have no real query → keep the profile, skip query-driven retrieval.
    system = await assemble_context(host, query, SYSTEM, retrieve=not trivial)
    if convo.summary:
        system = f"{system}\n\n# Conversation so far\n{convo.summary}"
    if roster:
        system = (
            f"{system}\n\n# Your other threads\nYou have other chats/tasks open. You know they "
            f"exist and their status, but not their contents:\n{roster}"
        )

    tools = host.tools_for_model()
    if allow_delegate:
        tools = [*tools, DELEGATE_TOOL, VERIFY_TOOL]
    start_len = len(convo.messages)  # roll back to here if the turn is stopped (keeps alternation)
    convo.messages.append({"role": "user", "content": user_message})
    try:
        return await _run_loop(convo, system, tools, provider, host, ask, approver)
    except asyncio.CancelledError:
        del convo.messages[start_len:]  # discard the stopped turn — no orphaned tool_use
        raise


async def _run_loop(
    convo: Conversation,
    system: str,
    tools: list[Any],
    provider: ModelProvider,
    host: MCPHost,
    ask: Ask | None,
    approver: "Approver | None",
) -> str:
    iterations = 0
    while True:
        iterations += 1
        if iterations == WARN_ITERATIONS:
            _log.warning("turn still running after %d tool iterations…", WARN_ITERATIONS)
        if iterations > MAX_ITERATIONS:
            _log.error("turn hit the %d-iteration cap; stopping", MAX_ITERATIONS)
            stopped = f"[stopped after {MAX_ITERATIONS} tool iterations]"
            convo.messages.append({"role": "assistant", "content": stopped})  # keep alternation
            return stopped
        response = await provider.generate(system=system, messages=convo.messages, tools=tools)
        convo.messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if isinstance(block, TextBlock)
            )

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if not isinstance(block, ToolUseBlock):
                continue
            args = cast("dict[str, Any]", block.input)
            if block.name == "delegate":
                results = await run_subagents(args.get("tasks", []), provider, host)
                text, is_error = json.dumps(results), False
            elif block.name == "verify_claims":
                verdicts = await verify_claims(args.get("claims", []), provider, host)
                text, is_error = json.dumps(verdicts), False
            elif block.name in APPROVAL_REQUIRED and not (
                approver is not None and await approver.approve(block.name, args, ask)
            ):
                text, is_error = "[denied — needs your approval in an interactive session]", True
            else:
                text, is_error = await host.call_tool(block.name, args)
            capped = _cap(text)
            if capped is not text:
                _log.info("capped %s result: %d -> %d chars", block.name, len(text), len(capped))
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": capped,
                    "is_error": is_error,
                }
            )
        convo.messages.append({"role": "user", "content": tool_results})
