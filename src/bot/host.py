"""Minimal MCP host: spawn the obsidian server over stdio, aggregate + route tools."""

import os
import sys
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client


class MCPHost:
    """Holds one stdio MCP server (obsidian) open for the process lifetime."""

    def __init__(self, vault_path: str, index_path: str) -> None:
        self._vault_path = vault_path
        self._index_path = index_path
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._tools: list[dict[str, Any]] = []

    async def __aenter__(self) -> "MCPHost":
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "bot.servers.obsidian.server"],
            env={
                "VAULT_PATH": self._vault_path,
                "INDEX_PATH": self._index_path,
                "PATH": os.environ.get("PATH", ""),
            },
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listed = await session.list_tools()
        self._session = session
        self._tools = [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
            for tool in listed.tools
        ]
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
        """Route a tool call to its server; return (text, is_error)."""
        if self._session is None:
            raise RuntimeError("host not started")
        result = await self._session.call_tool(name, arguments)
        text = "".join(
            block.text
            for block in result.content
            if isinstance(block, types.TextContent)
        )
        return text, bool(result.isError)
