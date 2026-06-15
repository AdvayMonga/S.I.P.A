"""memory MCP server: the bot's model of you — profile + episodic recall, separate from the vault.

Tool-driven for M5 (the model calls these like it calls vault_search); automatic per-turn profile
injection is Context-assembly v2 (VISION §5.9). Store is the source of truth, persistent — no
reindex on start, unlike the vault-derived indexes."""

import json
import logging
import os
import warnings
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from embedding import FastEmbedEmbedder
from servers.memory.store import MemoryStore

# Quiet fastembed model download/load noise (model imports lazily on first embed).
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
warnings.filterwarnings("ignore", message="Cannot enable progress bars")
for _name in ("httpx", "huggingface_hub", "fastembed"):
    logging.getLogger(_name).setLevel(logging.WARNING)

mcp = FastMCP("memory")
_store = MemoryStore(os.environ.get("MEMORY_DB", "data/memory.db"), FastEmbedEmbedder())


@mcp.tool()
def memory_get_profile() -> str:
    """The always-available core: standing preferences, instructions, key entities, house style."""
    return _store.get_profile()


@mcp.tool()
def memory_recall(query: str, k: int = 5, kind: str = "") -> str:
    """Recall distilled facts/episodes by meaning. Optional kind filter. Returns JSON hits."""
    return json.dumps(_store.recall(query, k=k, kind=kind or None))


@mcp.tool()
def memory_list(tier: str = "", kind: str = "", status: str = "active") -> str:
    """Audit the store: list entries (no vectors), filtered by tier/kind/status. Returns JSON.
    status='all' shows everything incl. stale/deleted history; '' tier/kind means no filter."""
    return json.dumps(
        _store.list_entries(tier=tier or None, kind=kind or None, status=status)
    )


@mcp.tool()
def memory_list_open_tasks() -> str:
    """Open tasks carried across sessions (working memory). Returns JSON."""
    return json.dumps(_store.list_open_tasks())


@mcp.tool()
def memory_remember(content: str, kind: str, keys: str = "") -> str:
    """Distill a durable entry. kind ∈ preference|instruction|entity|house_style|fact|episode|task.
    Tier is inferred from kind. keys = optional space-separated tags for conflict detection."""
    entry_id = _store.remember(content, kind, datetime.now(), keys=keys)
    return f"Remembered [{entry_id}] ({kind})"


@mcp.tool()
def memory_update(id: int, content: str) -> str:
    """Supersede entry `id` with new content; the old entry is kept as stale history."""
    new_id = _store.update(id, content, datetime.now())
    if new_id is None:
        return f"No active entry: {id}"
    return f"Updated {id} → [{new_id}]"


@mcp.tool()
def memory_forget(id: int) -> str:
    """Soft-delete an entry (excluded from all reads)."""
    return f"Forgot {id}" if _store.forget(id) else f"No such entry: {id}"


@mcp.tool()
def memory_complete_task(id: int) -> str:
    """Mark an open task done — drops it from the open-tasks list, keeps it as history."""
    return f"Completed {id}" if _store.mark_done(id) else f"No open task: {id}"


@mcp.tool()
def memory_consolidate() -> str:
    """Mechanical cleanup: dedup by keys (newest wins) + evict oldest profile over cap. JSON."""
    return json.dumps(_store.consolidate())


if __name__ == "__main__":
    mcp.run()
