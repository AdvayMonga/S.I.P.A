from pathlib import Path

from servers.obsidian import index

from vaultfs import vault


def _db(tmp_path: Path) -> Path:
    return tmp_path / "data" / "index.db"


def test_reindex_and_search_ranks(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "the quick brown fox jumps")
    vault.create_note(tmp_path, "b.md", "a note about databases and indexing")
    db = _db(tmp_path)
    assert index.reindex(db, tmp_path) == 2

    hits = index.search(db, "fox")
    assert [h["path"] for h in hits] == ["a.md"]
    assert "fox" in hits[0]["snippet"]

    db_hits = index.search(db, "databases")
    assert [h["path"] for h in db_hits] == ["b.md"]


def test_search_empty_query(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "content")
    db = _db(tmp_path)
    index.reindex(db, tmp_path)
    assert index.search(db, "   ") == []


def test_upsert_reflects_new_content(tmp_path: Path) -> None:
    db = _db(tmp_path)
    index.reindex(db, tmp_path)
    assert index.search(db, "alpha") == []
    index.upsert(db, "x.md", "alpha beta")
    assert [h["path"] for h in index.search(db, "alpha")] == ["x.md"]
    # upsert again replaces, not duplicates
    index.upsert(db, "x.md", "gamma only")
    assert index.search(db, "alpha") == []
    assert [h["path"] for h in index.search(db, "gamma")] == ["x.md"]


def test_delete_removes(tmp_path: Path) -> None:
    db = _db(tmp_path)
    index.upsert(db, "x.md", "findme")
    assert index.search(db, "findme")
    index.delete(db, "x.md")
    assert index.search(db, "findme") == []


def test_special_chars_dont_break_query(tmp_path: Path) -> None:
    db = _db(tmp_path)
    index.upsert(db, "x.md", "a quoted phrase here")
    # FTS operators / quotes in the query must not raise
    assert index.search(db, 'quoted "phrase') is not None
    assert index.search(db, "OR AND NOT") == []
