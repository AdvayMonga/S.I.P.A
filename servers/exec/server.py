"""exec MCP server: run shell commands in a configured working directory.

The dangerous capability — gated hard:
- Spawns only when EXEC_ROOT is set (empty = no shell access at all).
- Commands run with cwd = EXEC_ROOT, a timeout, and capped output.
- The host marks `run_shell` approval-required (loop.APPROVAL_REQUIRED): interactive turns ask the
  user; unattended turns (timer, background sub-agents) are denied — no autonomous shell without a
  sandbox (VISION's autonomy-last rule)."""

import asyncio
import os

from mcp.server.fastmcp import FastMCP

_ROOT = os.environ.get("EXEC_ROOT", "")
_TIMEOUT = 30.0
_MAX_CHARS = 20_000

mcp = FastMCP("exec")


async def run_command(command: str, root: str, timeout: float = _TIMEOUT) -> str:
    """Run `command` in `root`; return exit code + combined stdout/stderr (truncated)."""
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return f"[timed out after {timeout:g}s]"
    text = out.decode(errors="replace")
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n[...truncated]"
    return f"(exit {proc.returncode})\n{text}".strip()


@mcp.tool()
async def run_shell(command: str) -> str:
    """Run a shell command in the working directory and return its exit code + output. Use for
    computation, builds, tests, scripted file work. Confined to one directory; runs only with the
    user's approval in an interactive session."""
    if not _ROOT:
        return "[error] exec is not configured (set EXEC_ROOT)"
    return await run_command(command, _ROOT)


if __name__ == "__main__":
    mcp.run()
