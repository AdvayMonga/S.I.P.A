"""fs MCP server: read-only access to local files, confined to configured roots.

Only spawned when FS_READ_ROOTS (os.pathsep-separated absolute dirs) is set — empty = no fs access.
Paths are resolved (following symlinks) and must sit under a root, so there's no escaping via `..`
or a symlink. Read-only by design; write/exec is a separate, gated capability."""

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_MAX_CHARS = 100_000
_ROOTS = [
    Path(r).expanduser().resolve()
    for r in os.environ.get("FS_READ_ROOTS", "").split(os.pathsep)
    if r
]

mcp = FastMCP("fs")


def resolve_within(path: str, roots: list[Path]) -> Path:
    """Resolve `path` and require it to sit inside one of `roots`, else raise. Pure + testable."""
    resolved = Path(path).expanduser().resolve()
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ValueError(f"path is outside the allowed read roots: {path}")
    return resolved


@mcp.tool()
def read_file(path: str) -> str:
    """Read a UTF-8 text file (truncated if very large). Confined to the configured read roots."""
    try:
        data = resolve_within(path, _ROOTS).read_text(encoding="utf-8")
    except ValueError as exc:
        return f"[denied] {exc}"
    except (OSError, UnicodeDecodeError) as exc:
        return f"[error] {exc}"
    return data[:_MAX_CHARS]


@mcp.tool()
def list_dir(path: str) -> str:
    """List a directory's entries as JSON [{name, dir}]. Confined to the configured read roots."""
    try:
        target = resolve_within(path, _ROOTS)
        entries = [{"name": c.name, "dir": c.is_dir()} for c in sorted(target.iterdir())]
    except ValueError as exc:
        return json.dumps({"error": f"denied: {exc}"})
    except OSError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps(entries)


if __name__ == "__main__":
    mcp.run()
