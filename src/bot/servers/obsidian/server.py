"""Obsidian MCP server: one tool, vault_create_note, over stdio."""

import os

from mcp.server.fastmcp import FastMCP

from bot.servers.obsidian.vault import create_note

mcp = FastMCP("obsidian")


@mcp.tool()
def vault_create_note(path: str, content: str) -> str:
    """Create a new Markdown note at `path` (relative to the vault root).

    Fails if a note already exists at that path. Returns the created path.
    """
    vault_root = os.environ["VAULT_PATH"]
    created = create_note(vault_root, path, content)
    return f"Created note: {created}"


if __name__ == "__main__":
    mcp.run()
