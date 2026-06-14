import hashlib
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from servers.memory.store import PROFILE_CAP, MemoryStore


class StubEmbedder:
    """Deterministic bag-of-words bucket vectors — exercises recall without fastembed."""

    dim = 16

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            for word in text.lower().split():
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
            out.append(vec)
        return out


def _store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "data" / "memory.db", StubEmbedder())


NOW = datetime(2026, 6, 13, 9, 0)


def test_profile_concat_and_tier_inference(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.remember("likes terse replies", "preference", NOW)
    store.remember("uses kebab-case note names", "house_style", NOW)
    profile = store.get_profile()
    assert "[preference] likes terse replies" in profile
    assert "[house_style] uses kebab-case note names" in profile


def test_recall_by_meaning(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.remember("machine learning and neural networks", "fact", NOW)
    store.remember("onions garlic tomatoes recipe", "fact", NOW)
    hits = store.recall("neural networks machine", k=2)
    assert hits[0]["content"].startswith("machine learning")


def test_recall_excludes_profile_tier(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.remember("likes terse replies", "preference", NOW)  # profile, not embedded
    assert store.recall("terse replies") == []


def test_recall_kind_filter(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.remember("met alice about the roadmap", "episode", NOW)
    store.remember("alice prefers email", "fact", NOW)
    hits = store.recall("alice", k=5, kind="episode")
    assert {h["kind"] for h in hits} == {"episode"}


def test_invalid_kind(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _store(tmp_path).remember("x", "nonsense", NOW)


def test_open_tasks_lifecycle(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tid = store.remember("ship M5", "task", NOW)
    assert [t["id"] for t in store.list_open_tasks()] == [tid]
    assert store.mark_done(tid) is True
    assert store.list_open_tasks() == []
    assert store.mark_done(tid) is False  # no longer active


def test_update_supersedes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    old = store.remember("old fact", "fact", NOW)
    new = store.update(old, "new fact", NOW)
    assert new is not None and new != old
    contents = [h["content"] for h in store.recall("fact", k=5)]
    assert "new fact" in contents and "old fact" not in contents
    assert store.update(old, "again", NOW) is None  # already stale


def test_forget(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fid = store.remember("forget me", "fact", NOW)
    assert store.forget(fid) is True
    assert store.recall("forget me") == []
    assert store.forget(fid) is False  # already deleted


def test_consolidate_dedup_by_keys(tmp_path: Path) -> None:
    store = _store(tmp_path)
    a = store.remember("address v1", "fact", datetime(2026, 6, 1), keys="home-address")
    b = store.remember("address v2", "fact", datetime(2026, 6, 13), keys="home-address")
    store.remember("unrelated", "fact", NOW, keys="other")
    result = store.consolidate()
    assert result["superseded"] == 1
    contents = [h["content"] for h in store.recall("address", k=5)]
    assert "address v2" in contents and "address v1" not in contents
    assert a != b  # both were distinct entries; older is now stale


def test_consolidate_profile_cap(tmp_path: Path) -> None:
    store = _store(tmp_path)
    big = "x" * (PROFILE_CAP // 2 + 50)
    store.remember(big, "preference", datetime(2026, 6, 1))  # oldest
    store.remember(big, "preference", datetime(2026, 6, 13))
    result = store.consolidate()
    assert result["profile_evicted"] == 1
    assert len(store.get_profile()) <= PROFILE_CAP
