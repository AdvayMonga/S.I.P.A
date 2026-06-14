"""vault-search MCP server: recall the vault by meaning (hybrid vector + keyword)."""

import json
import logging
import os
import warnings

from mcp.server.fastmcp import FastMCP

from embedding import FastEmbedEmbedder
from servers.vault_search.index import SemanticIndex

# Quiet model download/load noise. fastembed imports lazily on first embed, so setting these at
# module load (before any reindex) is early enough.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
warnings.filterwarnings("ignore", message="Cannot enable progress bars")
for _name in ("httpx", "huggingface_hub", "fastembed"):
    logging.getLogger(_name).setLevel(logging.WARNING)

mcp = FastMCP("vault_search")
_index = SemanticIndex(os.environ.get("VSEARCH_DB", "data/vault_search.db"), FastEmbedEmbedder())


@mcp.tool()
def semantic_search(query: str, k: int = 5) -> str:
    """Recall vault chunks by meaning — hybrid vector + keyword. Returns JSON hits."""
    return json.dumps(_index.search(query, k=k))


@mcp.tool()
def index_status() -> str:
    """Counts of indexed chunks and notes."""
    return json.dumps(_index.status())


if __name__ == "__main__":
    _index.reindex(os.environ["VAULT_PATH"])  # embed the vault on start (picks up manual edits)
    mcp.run()
