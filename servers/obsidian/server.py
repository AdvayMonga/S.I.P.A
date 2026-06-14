"""Obsidian MCP server: the ten vault_ tools over stdio. Mutations are git-committed + reindexed."""

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from servers.obsidian import index
from vaultfs import vault, vault_git

mcp = FastMCP("obsidian")


def _root() -> str:
    return os.environ["VAULT_PATH"]


def _index() -> str:
    return os.environ["INDEX_PATH"]


def _committed(action: str, warnings: list[str]) -> str:
    rev = vault_git.commit(_root(), action)
    message = f"{action} (commit {rev})" if rev else action
    if warnings:
        message += " | unresolved links: " + ", ".join(warnings)
    return message


# --- reads --------------------------------------------------------------------


@mcp.tool()
def vault_read_note(path: str) -> str:
    """Read a note's raw Markdown content."""
    return vault.read_note(_root(), path)


@mcp.tool()
def vault_list_notes(folder: str | None = None) -> list[str]:
    """List note paths under `folder` (or the whole vault). Excludes trashed notes."""
    return vault.list_notes(_root(), folder)


@mcp.tool()
def vault_search_text(query: str, limit: int = 20, regex: bool = False) -> list[dict[str, Any]]:
    """Search notes. Keyword (BM25-ranked, default) or `regex=True` (exact line scan)."""
    if regex:
        return vault.search_text(_root(), query, limit=limit, regex=True)
    return index.search(_index(), query, limit=limit)


@mcp.tool()
def vault_resolve_link(title: str) -> str | None:
    """Find a note's path by its title (filename stem), for linking. Null if none."""
    return vault.resolve_link(_root(), title)


@mcp.tool()
def vault_get_backlinks(path: str) -> list[str]:
    """List notes that link to the given note via `[[wikilinks]]`."""
    return vault.get_backlinks(_root(), path)


# --- writes (atomic + git-committed + reindexed) ------------------------------


@mcp.tool()
def vault_create_note(
    path: str, content: str, frontmatter: dict[str, Any] | None = None
) -> str:
    """Create a new Markdown note (fails if it exists). Optional frontmatter dict."""
    root = _root()
    created = vault.create_note(root, path, content, frontmatter)
    final = created.read_text(encoding="utf-8")
    index.upsert(_index(), path, final)
    return _committed(f"create {path}", vault.unresolved_links(root, final))


@mcp.tool()
def vault_append(path: str, content: str, under_heading: str | None = None) -> str:
    """Non-destructively append `content` to a note, optionally under a heading."""
    root = _root()
    written = vault.append_note(root, path, content, under_heading=under_heading)
    index.upsert(_index(), path, written.read_text(encoding="utf-8"))
    return _committed(f"append {path}", vault.unresolved_links(root, content))


@mcp.tool()
def vault_patch_section(path: str, heading: str, content: str) -> str:
    """Replace the body under `heading` in a note (surgical edit). Heading must exist."""
    root = _root()
    written = vault.patch_section(root, path, heading, content)
    index.upsert(_index(), path, written.read_text(encoding="utf-8"))
    return _committed(f"patch {path} #{heading}", vault.unresolved_links(root, content))


@mcp.tool()
def vault_move_note(old: str, new: str) -> str:
    """Rename/move a note and rewrite inbound `[[links]]`."""
    root = _root()
    dst, updated = vault.move_note(root, old, new)
    index.delete(_index(), old)
    index.upsert(_index(), new, dst.read_text(encoding="utf-8"))
    message = _committed(f"move {old} -> {new}", [])
    if updated:
        message += f" | relinked: {', '.join(updated)}"
    return message


@mcp.tool()
def vault_trash_note(path: str) -> str:
    """Soft-delete a note to `/_trash` (recoverable; no hard delete)."""
    root = _root()
    dst = vault.trash_note(root, path)
    index.delete(_index(), path)
    return _committed(f"trash {path} -> {dst.name}", [])


if __name__ == "__main__":
    index.reindex(_index(), _root())  # rebuild from the vault (picks up manual edits)
    mcp.run()
