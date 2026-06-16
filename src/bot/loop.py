"""Stateless agent loop: model call -> tool calls -> repeat until a final answer."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from anthropic.types import TextBlock, ToolUseBlock

from .context import assemble_context
from .conversation import Conversation, maybe_compact
from .host import MCPHost
from .provider import ModelProvider
from .subagent import DELEGATE_BACKGROUND_TOOL, DELEGATE_TOOL, run_subagents

_log = logging.getLogger("sipa.loop")

WARN_ITERATIONS = 15  # soft: log and keep going — don't interrupt a legitimately long task
MAX_ITERATIONS = 40  # hard backstop: stop a runaway turn (tool calls that never converge)

SYSTEM = (
    "You are S.I.P.A., a personal assistant with access to an Obsidian vault. "
    "When the user asks you to save, note, or write something down, create a note "
    "with the vault tools. Choose a sensible Markdown path and title. "
    "Answer directly and concisely."
)


async def run_turn(
    convo: Conversation,
    user_message: str,
    provider: ModelProvider,
    host: MCPHost,
    *,
    allow_delegate: bool = False,
    spawn_background: Callable[[str], Awaitable[str]] | None = None,
) -> str:
    """Run one user turn to completion, mutating `convo` in place. `allow_delegate` offers the
    `delegate`/`delegate_background` tools — only top-level turns set it, so sub-agents can't
    recurse. `spawn_background` starts a detached background sub-agent."""
    await maybe_compact(convo, provider)  # bound the window before we build the turn
    # Enrich the retrieval query with the rolling summary so follow-ups retrieve against state.
    query = f"{convo.summary[-500:]} {user_message}".strip() if convo.summary else user_message
    # Assemble context once on the query; reuse it across this turn's tool-use iterations.
    system = await assemble_context(host, query, SYSTEM)
    if convo.summary:
        system = f"{system}\n\n# Conversation so far\n{convo.summary}"

    tools = host.tools_for_model()
    if allow_delegate:
        tools = [*tools, DELEGATE_TOOL, DELEGATE_BACKGROUND_TOOL]
    convo.messages.append({"role": "user", "content": user_message})
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
            elif block.name == "delegate_background":
                if spawn_background is None:
                    text, is_error = "background delegation unavailable", True
                else:
                    text, is_error = await spawn_background(args.get("task", "")), False
            else:
                text, is_error = await host.call_tool(block.name, args)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": text,
                    "is_error": is_error,
                }
            )
        convo.messages.append({"role": "user", "content": tool_results})
