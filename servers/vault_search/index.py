"""Semantic index: heading-aware chunks + embeddings, hybrid (vector + FTS5) retrieval via RRF.

Brute-force NumPy cosine for vectors — this Python's sqlite3 can't load extensions, so no
sqlite-vec. Fine at personal-vault scale; sqlite-vec/LanceDB are the scale path (see BACKLOG).
"""

import re
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from embedding import Embedder
from servers.vault_search import chunk as chunking
from vaultfs import vault

_RRF_K = 60


class SemanticIndex:
    def __init__(self, db_path: str | Path, embedder: Embedder) -> None:
        self._db = str(db_path)
        self._embedder = embedder

    def _connect(self) -> sqlite3.Connection:
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._db)
        con.execute(
            "CREATE TABLE IF NOT EXISTS chunks"
            "(id INTEGER PRIMARY KEY, path TEXT, heading TEXT, text TEXT, vec BLOB)"
        )
        con.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts "
            "USING fts5(text, tokenize='porter unicode61')"
        )
        return con

    def reindex(self, vault_root: str | Path) -> int:
        """Rebuild from the vault: chunk every note, embed, store. Returns the chunk count."""
        chunks: list[chunking.Chunk] = []
        for rel in vault.list_notes(vault_root):
            chunks.extend(chunking.chunk_note(rel, vault.read_note(vault_root, rel)))
        vectors = self._embedder.embed([c.text for c in chunks]) if chunks else []
        con = self._connect()
        try:
            con.execute("DELETE FROM chunks")
            con.execute("DELETE FROM chunks_fts")
            for chunk, vector in zip(chunks, vectors, strict=True):
                blob = np.asarray(vector, dtype=np.float32).tobytes()
                cursor = con.execute(
                    "INSERT INTO chunks(path, heading, text, vec) VALUES(?, ?, ?, ?)",
                    (chunk.path, chunk.heading, chunk.text, blob),
                )
                con.execute(
                    "INSERT INTO chunks_fts(rowid, text) VALUES(?, ?)",
                    (cursor.lastrowid, chunk.text),
                )
            con.commit()
            return len(chunks)
        finally:
            con.close()

    def status(self) -> dict[str, int]:
        con = self._connect()
        try:
            chunks = int(con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
            notes = int(con.execute("SELECT COUNT(DISTINCT path) FROM chunks").fetchone()[0])
            return {"chunks": chunks, "notes": notes}
        finally:
            con.close()

    def search(self, query: str, k: int = 5, pool: int = 20) -> list[dict[str, Any]]:
        """Hybrid retrieval: fuse vector + keyword rankings with Reciprocal Rank Fusion."""
        con = self._connect()
        try:
            rows = con.execute("SELECT id, path, heading, text, vec FROM chunks").fetchall()
            if not rows:
                return []
            vector_ranks, vector_sims = self._vector_ranks(query, rows, pool)
            keyword_ranks = self._keyword_ranks(con, query, pool)
            by_id = {row[0]: row for row in rows}
            scored: list[tuple[int, float]] = []
            for cid in set(vector_ranks) | set(keyword_ranks):
                score = 0.0
                if cid in vector_ranks:
                    score += 1.0 / (_RRF_K + vector_ranks[cid])
                if cid in keyword_ranks:
                    score += 1.0 / (_RRF_K + keyword_ranks[cid])
                scored.append((cid, score))
            scored.sort(key=lambda item: -item[1])
            return [
                {
                    "path": by_id[cid][1],
                    "heading": by_id[cid][2],
                    "snippet": _snippet(by_id[cid][3]),
                    "score": round(score, 4),  # RRF rank-fusion (ordering)
                    "sim": round(vector_sims.get(cid, 0.0), 4),  # raw vector cosine (relevance)
                }
                for cid, score in scored[:k]
            ]
        finally:
            con.close()

    def _vector_ranks(
        self, query: str, rows: list[Any], pool: int
    ) -> tuple[dict[int, int], dict[int, float]]:
        """Top-`pool` by vector cosine: (id→rank for RRF, id→cosine for relevance)."""
        qv = np.asarray(self._embedder.embed([query])[0], dtype=np.float32)
        mat = np.array([np.frombuffer(row[4], dtype=np.float32) for row in rows])
        sims = mat @ qv / (np.linalg.norm(mat, axis=1) * np.linalg.norm(qv) + 1e-9)
        order = np.argsort(-sims)[:pool]
        ranks = {int(rows[int(i)][0]): rank for rank, i in enumerate(order)}
        sim_by_id = {int(rows[int(i)][0]): float(sims[int(i)]) for i in order}
        return ranks, sim_by_id

    def _keyword_ranks(self, con: sqlite3.Connection, query: str, pool: int) -> dict[int, int]:
        terms = [t for t in re.split(r"\s+", query.strip()) if t]
        if not terms:
            return {}
        match = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
        rows = con.execute(
            "SELECT rowid, bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ? "
            "ORDER BY bm25(chunks_fts) LIMIT ?",
            (match, pool),
        ).fetchall()
        return {int(rowid): rank for rank, (rowid, _score) in enumerate(rows)}


def _snippet(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"
