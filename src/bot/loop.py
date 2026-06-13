"""Stateless agent loop: model call -> tool calls -> repeat until a final answer."""

from typing import Any, cast

from anthropic.types import TextBlock, ToolUseBlock

from .host import MCPHost
from .provider import ModelProvider

SYSTEM = (
    "You are S.I.P.A., a personal assistant with access to an Obsidian vault. "
    "When the user asks you to save, note, or write something down, create a note "
    "with the vault tools. Choose a sensible Markdown path and title. "
    "Answer directly and concisely."
)


async def run_turn(
    history: list[Any],
    user_message: str,
    provider: ModelProvider,
    host: MCPHost,
) -> str:
    """Run one user turn to completion, mutating `history` in place."""
    history.append({"role": "user", "content": user_message})
    while True:
        response = await provider.generate(
            system=SYSTEM, messages=history, tools=host.tools_for_model()
        )
        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if isinstance(block, TextBlock)
            )

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if not isinstance(block, ToolUseBlock):
                continue
            args = cast("dict[str, Any]", block.input)
            text, is_error = await host.call_tool(block.name, args)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": text,
                    "is_error": is_error,
                }
            )
        history.append({"role": "user", "content": tool_results})
