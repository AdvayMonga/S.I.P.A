"""MCP host: spawn N servers over stdio, aggregate their tools, route each call to its server."""

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


def _to_content(blocks: list[Any]) -> Any:
    """MCP tool-result content → Anthropic content. A plain string when it's all text (the common
    case, back-compatible), else a list of text/image blocks so images reach the model (vision)."""
    if all(isinstance(b, types.TextContent) for b in blocks):
        return "".join(b.text for b in blocks)
    out: list[dict[str, Any]] = []
    for b in blocks:
        if isinstance(b, types.TextContent):
            out.append({"type": "text", "text": b.text})
        elif isinstance(b, types.ImageContent):
            out.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": b.mimeType, "data": b.data},
                }
            )
    return out


class MCPHost:
    """Holds a set of named stdio MCP servers open for the process lifetime."""

    def __init__(self, servers: dict[str, StdioServerParameters]) -> None:
        self._servers = servers
        self._stack = AsyncExitStack()
        self._tool_session: dict[str, ClientSession] = {}
        self._tools: list[dict[str, Any]] = []

    async def __aenter__(self) -> "MCPHost":
        for params in self._servers.values():
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            for tool in (await session.list_tools()).tools:
                self._tool_session[tool.name] = session
                self._tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema,
                    }
                )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._stack.aclose()

    def tools_for_model(self) -> list[Any]:
        return self._tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[Any, bool]:
        """Route a tool call to its owning server; return (content, is_error). content is a string
        for text tools, or a list of text/image blocks when the tool returns an image (vision)."""
        session = self._tool_session.get(name)
        if session is None:
            raise RuntimeError(f"unknown tool: {name}")
        result = await session.call_tool(name, arguments)
        return _to_content(result.content), bool(result.isError)
