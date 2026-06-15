"""Memory store: the bot's model of you. One SQLite table, two tiers, vector-only recall.

Source of truth (not a rebuildable index) — lives in gitignored data/, no remote backup (see
design/memory-server.md). `created_at` is injected (a `now` param) for deterministic tests,
mirroring the scheduler's store. No MCP here."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from embedding import Embedder

# kind → tier. memory_remember takes only a kind; the tier follows from it (matches VISION §5.8).
KIND_TIER = {
    "preference": "profile",
    "instruction": "profile",
    "entity": "profile",
    "house_style": "profile",
    "fact": "recall",
    "episode": "recall",
    "task": "recall",
}
PROFILE_CAP = 2000  # chars of active profile content before consolidate evicts oldest


class MemoryStore:
    def __init__(self, db_path: str | Path, embedder: Embedder) -> None:
        self._db = str(db_path)
        self._embedder = embedder

    def _connect(self) -> sqlite3.Connection:
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._db)
        con.execute(
            "CREATE TABLE IF NOT EXISTS memory("
            "id INTEGER PRIMARY KEY, tier TEXT, kind TEXT, content TEXT, keys TEXT, "
            "status TEXT, vec BLOB, created_at TEXT, superseded_by INTEGER)"
        )
        return con

    # --- writes ---------------------------------------------------------------

    def remember(self, content: str, kind: str, now: datetime, keys: str = "") -> int:
        """Add a durable entry. Recall-tier entries are embedded; profile entries are not."""
        if kind not in KIND_TIER:
            raise ValueError(f"kind must be one of {sorted(KIND_TIER)}")
        tier = KIND_TIER[kind]
        blob = self._embed(content) if tier == "recall" else None
        con = self._connect()
        try:
            cur = con.execute(
                "INSERT INTO memory(tier, kind, content, keys, status, vec, created_at) "
                "VALUES(?, ?, ?, ?, 'active', ?, ?)",
                (tier, kind, content, keys, blob, now.isoformat()),
            )
            con.commit()
            return int(cur.lastrowid or 0)
        finally:
            con.close()

    def update(self, entry_id: int, content: str, now: datetime) -> int | None:
        """Supersede: write a new active entry, mark the old one stale (keeps history)."""
        con = self._connect()
        try:
            row = con.execute(
                "SELECT tier, kind, keys FROM memory WHERE id=? AND status='active'", (entry_id,)
            ).fetchone()
            if row is None:
                return None
            tier, kind, keys = row
            blob = self._embed(content) if tier == "recall" else None
            cur = con.execute(
                "INSERT INTO memory(tier, kind, content, keys, status, vec, created_at) "
                "VALUES(?, ?, ?, ?, 'active', ?, ?)",
                (tier, kind, content, keys, blob, now.isoformat()),
            )
            new_id = int(cur.lastrowid or 0)
            con.execute(
                "UPDATE memory SET status='stale', superseded_by=? WHERE id=?", (new_id, entry_id)
            )
            con.commit()
            return new_id
        finally:
            con.close()

    def forget(self, entry_id: int) -> bool:
        """Soft delete: status='deleted', excluded from all reads."""
        con = self._connect()
        try:
            cur = con.execute(
                "UPDATE memory SET status='deleted' WHERE id=? AND status!='deleted'", (entry_id,)
            )
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    def mark_done(self, entry_id: int) -> bool:
        """Mark an open task done (drops it from list_open_tasks)."""
        con = self._connect()
        try:
            cur = con.execute(
                "UPDATE memory SET status='done' WHERE id=? AND kind='task' AND status='active'",
                (entry_id,),
            )
            con.commit()
            return cur.rowcount > 0
        finally:
            con.close()

    # --- reads ----------------------------------------------------------------

    def get_profile(self) -> str:
        """Concat active profile entries (oldest first), grouped by kind, under the char cap."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT kind, content FROM memory WHERE tier='profile' AND status='active' "
                "ORDER BY created_at, id"
            ).fetchall()
        finally:
            con.close()
        lines = [f"[{kind}] {content}" for kind, content in rows]
        text = "\n".join(lines)
        return text[:PROFILE_CAP] if len(text) > PROFILE_CAP else text

    def recall(self, query: str, k: int = 5, kind: str | None = None) -> list[dict[str, Any]]:
        """Embed the query, cosine over active recall entries, return top-k."""
        con = self._connect()
        try:
            sql = (
                "SELECT id, kind, content, vec FROM memory "
                "WHERE tier='recall' AND status='active'"
            )
            params: list[Any] = []
            if kind is not None:
                sql += " AND kind=?"
                params.append(kind)
            rows = con.execute(sql, params).fetchall()
        finally:
            con.close()
        rows = [r for r in rows if r[3] is not None]
        if not rows:
            return []
        qv = np.asarray(self._embedder.embed([query])[0], dtype=np.float32)
        mat = np.array([np.frombuffer(r[3], dtype=np.float32) for r in rows])
        sims = mat @ qv / (np.linalg.norm(mat, axis=1) * np.linalg.norm(qv) + 1e-9)
        order = np.argsort(-sims)[:k]
        return [
            {
                "id": int(rows[int(i)][0]),
                "kind": rows[int(i)][1],
                "content": rows[int(i)][2],
                "score": round(float(sims[int(i)]), 4),
            }
            for i in order
        ]

    def list_entries(
        self, tier: str | None = None, kind: str | None = None, status: str = "active"
    ) -> list[dict[str, Any]]:
        """Browse the store for auditing (no vec). status='all' lifts the status filter."""
        sql = (
            "SELECT id, tier, kind, content, keys, status, created_at, superseded_by "
            "FROM memory"
        )
        clauses: list[str] = []
        params: list[Any] = []
        if status != "all":
            clauses.append("status=?")
            params.append(status)
        if tier is not None:
            clauses.append("tier=?")
            params.append(tier)
        if kind is not None:
            clauses.append("kind=?")
            params.append(kind)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at, id"
        con = self._connect()
        try:
            rows = con.execute(sql, params).fetchall()
        finally:
            con.close()
        cols = ("id", "tier", "kind", "content", "keys", "status", "created_at", "superseded_by")
        return [dict(zip(cols, row, strict=True)) for row in rows]

    def list_open_tasks(self) -> list[dict[str, Any]]:
        """Active kind='task' entries — working memory carried across sessions."""
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT id, content, keys, created_at FROM memory "
                "WHERE kind='task' AND status='active' ORDER BY created_at, id"
            ).fetchall()
        finally:
            con.close()
        return [
            {"id": int(r[0]), "content": r[1], "keys": r[2], "created_at": r[3]} for r in rows
        ]

    # --- consolidation (mechanical, no LLM) -----------------------------------

    def consolidate(self) -> dict[str, int]:
        """Dedup by keys (newest wins), then evict oldest profile entries over the cap."""
        con = self._connect()
        try:
            superseded = self._dedup_by_keys(con)
            profile_evicted = self._evict_profile(con)
            con.commit()
        finally:
            con.close()
        return {"superseded": superseded, "profile_evicted": profile_evicted}

    def _dedup_by_keys(self, con: sqlite3.Connection) -> int:
        """Active entries sharing non-empty keys → keep newest, mark the rest stale."""
        rows = con.execute(
            "SELECT id, keys FROM memory WHERE status='active' AND keys!='' "
            "ORDER BY created_at, id"
        ).fetchall()
        groups: dict[str, list[int]] = {}
        for entry_id, keys in rows:
            groups.setdefault(keys, []).append(int(entry_id))
        superseded = 0
        for ids in groups.values():
            if len(ids) < 2:
                continue
            keep = ids[-1]  # newest (rows ordered oldest→newest)
            for old in ids[:-1]:
                con.execute(
                    "UPDATE memory SET status='stale', superseded_by=? WHERE id=?", (keep, old)
                )
                superseded += 1
        return superseded

    def _evict_profile(self, con: sqlite3.Connection) -> int:
        """While active profile content exceeds the cap, supersede the oldest profile entry."""
        rows = con.execute(
            "SELECT id, content FROM memory WHERE tier='profile' AND status='active' "
            "ORDER BY created_at, id"
        ).fetchall()
        total = sum(len(content) for _id, content in rows)
        evicted = 0
        for entry_id, content in rows:
            if total <= PROFILE_CAP:
                break
            con.execute("UPDATE memory SET status='stale' WHERE id=?", (entry_id,))
            total -= len(content)
            evicted += 1
        return evicted

    def _embed(self, content: str) -> bytes:
        return np.asarray(self._embedder.embed([content])[0], dtype=np.float32).tobytes()
