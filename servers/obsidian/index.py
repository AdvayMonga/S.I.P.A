"""FTS5 keyword index over the vault. Derived + rebuildable; lives in data/, not the vault."""

import re
import sqlite3
from pathlib import Path
from typing import Any

from servers.obsidian import vault

_TABLE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS notes "
    "USING fts5(path UNINDEXED, content, tokenize='porter unicode61')"
)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(_TABLE)
    return con


def reindex(db_path: str | Path, vault_root: str | Path) -> int:
    """Rebuild the whole index from the vault. Returns the note count."""
    con = _connect(db_path)
    try:
        con.execute("DELETE FROM notes")
        count = 0
        for rel in vault.list_notes(vault_root):
            con.execute(
                "INSERT INTO notes(path, content) VALUES(?, ?)",
                (rel, vault.read_note(vault_root, rel)),
            )
            count += 1
        con.commit()
        return count
    finally:
        con.close()


def upsert(db_path: str | Path, path: str, content: str) -> None:
    con = _connect(db_path)
    try:
        con.execute("DELETE FROM notes WHERE path = ?", (path,))
        con.execute("INSERT INTO notes(path, content) VALUES(?, ?)", (path, content))
        con.commit()
    finally:
        con.close()


def delete(db_path: str | Path, path: str) -> None:
    con = _connect(db_path)
    try:
        con.execute("DELETE FROM notes WHERE path = ?", (path,))
        con.commit()
    finally:
        con.close()


def search(db_path: str | Path, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """BM25-ranked keyword search. Terms are quoted (AND) so arbitrary text is FTS-safe."""
    terms = [t for t in re.split(r"\s+", query.strip()) if t]
    if not terms:
        return []
    match = " ".join('"' + t.replace('"', '""') + '"' for t in terms)
    con = _connect(db_path)
    try:
        rows = con.execute(
            "SELECT path, snippet(notes, 1, '[', ']', '…', 12), bm25(notes) "
            "FROM notes WHERE notes MATCH ? ORDER BY bm25(notes) LIMIT ?",
            (match, limit),
        ).fetchall()
    finally:
        con.close()
    return [{"path": path, "snippet": snip, "score": round(score, 3)} for path, snip, score in rows]
