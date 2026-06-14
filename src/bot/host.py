"""MCP host: spawn N servers over stdio, aggregate their tools, route each call to its server."""

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


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

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """Route a tool call to its owning server; return (text, is_error)."""
        session = self._tool_session.get(name)
        if session is None:
            raise RuntimeError(f"unknown tool: {name}")
        result = await session.call_tool(name, arguments)
        text = "".join(
            block.text
            for block in result.content
            if isinstance(block, types.TextContent)
        )
        return text, bool(result.isError)
