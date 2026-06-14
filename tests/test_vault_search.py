import hashlib
from pathlib import Path

import numpy as np
from servers.obsidian import vault
from servers.vault_search import chunk as chunking
from servers.vault_search.index import SemanticIndex


class StubEmbedder:
    """Deterministic bag-of-words bucket vectors — enough to exercise the index, no fastembed."""

    dim = 16

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for word in text.lower().split():
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
            out.append(vec)
        return out


def test_chunk_by_heading() -> None:
    chunks = chunking.chunk_note("n.md", "intro line\n## One\nalpha beta\n## Two\ngamma")
    assert [c.heading for c in chunks] == ["", "One", "Two"]
    assert "alpha beta" in chunks[1].text


def test_chunk_strips_frontmatter() -> None:
    chunks = chunking.chunk_note("n.md", "---\ntitle: T\n---\n## H\nbody")
    assert all("title" not in c.text for c in chunks)
    assert chunks[0].heading == "H"


def test_reindex_status_and_search(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "ml.md", "## Notes\nmachine learning and neural networks")
    vault.create_note(tmp_path, "food.md", "## Recipe\nonions garlic tomatoes")
    idx = SemanticIndex(tmp_path / "data" / "vs.db", StubEmbedder())
    assert idx.reindex(tmp_path) == 2
    assert idx.status() == {"chunks": 2, "notes": 2}
    hits = idx.search("neural networks machine", k=2)
    assert hits[0]["path"] == "ml.md"


def test_search_empty_index(tmp_path: Path) -> None:
    idx = SemanticIndex(tmp_path / "data" / "vs.db", StubEmbedder())
    idx.reindex(tmp_path)
    assert idx.search("anything") == []
