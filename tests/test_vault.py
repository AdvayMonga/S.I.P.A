from pathlib import Path

import pytest
from servers.obsidian import vault

# --- create -------------------------------------------------------------------


def test_create_writes_file(tmp_path: Path) -> None:
    note = vault.create_note(tmp_path, "notes/hello.md", "# Hello")
    assert note == tmp_path / "notes" / "hello.md"
    assert note.read_text(encoding="utf-8") == "# Hello"


def test_create_refuses_overwrite(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "first")
    with pytest.raises(FileExistsError):
        vault.create_note(tmp_path, "a.md", "second")
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "first"


def test_path_traversal_blocked(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        vault.create_note(tmp_path, "../escape.md", "nope")
    assert not (tmp_path.parent / "escape.md").exists()


def test_extension_whitelist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        vault.create_note(tmp_path, "note.txt", "nope")


def test_create_with_frontmatter(tmp_path: Path) -> None:
    note = vault.create_note(tmp_path, "n.md", "body", {"tags": ["x"], "title": "N"})
    text = note.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "title: N" in text
    assert text.rstrip().endswith("body")


def test_malformed_frontmatter_rejected(tmp_path: Path) -> None:
    bad = "---\nfoo: [unclosed\n---\nbody"
    with pytest.raises(ValueError):
        vault.create_note(tmp_path, "bad.md", bad)
    assert not (tmp_path / "bad.md").exists()


# --- reads --------------------------------------------------------------------


def test_read_note(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "r.md", "content")
    assert vault.read_note(tmp_path, "r.md") == "content"
    with pytest.raises(FileNotFoundError):
        vault.read_note(tmp_path, "missing.md")


def test_list_notes_excludes_trash(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "a")
    vault.create_note(tmp_path, "sub/b.md", "b")
    vault.trash_note(tmp_path, "a.md")
    listed = vault.list_notes(tmp_path)
    assert listed == ["sub/b.md"]


def test_search_text(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "line one\nfind me here\nline three")
    vault.create_note(tmp_path, "b.md", "nothing relevant")
    hits = vault.search_text(tmp_path, "find me")
    assert len(hits) == 1
    assert hits[0]["path"] == "a.md"
    assert hits[0]["line"] == 2


def test_resolve_link_and_backlinks(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "People/Alice.md", "# Alice")
    vault.create_note(tmp_path, "log.md", "met [[Alice]] today")
    assert vault.resolve_link(tmp_path, "alice") == "People/Alice.md"
    assert vault.resolve_link(tmp_path, "nobody") is None
    assert vault.get_backlinks(tmp_path, "People/Alice.md") == ["log.md"]


# --- mutations ----------------------------------------------------------------


def test_append_to_end(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "first line")
    vault.append_note(tmp_path, "a.md", "second line")
    assert vault.read_note(tmp_path, "a.md") == "first line\nsecond line\n"


def test_append_under_heading(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "## One\nalpha\n## Two\nbeta\n")
    vault.append_note(tmp_path, "a.md", "added", under_heading="One")
    text = vault.read_note(tmp_path, "a.md")
    assert text == "## One\nalpha\nadded\n## Two\nbeta\n"


def test_append_missing_heading_errors(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "## One\nalpha\n")
    with pytest.raises(ValueError):
        vault.append_note(tmp_path, "a.md", "x", under_heading="Nope")


def test_patch_section(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "## One\nold\n## Two\nkeep\n")
    vault.patch_section(tmp_path, "a.md", "One", "new body")
    assert vault.read_note(tmp_path, "a.md") == "## One\nnew body\n## Two\nkeep\n"


def test_move_updates_links(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "Alice.md", "# Alice")
    vault.create_note(tmp_path, "log.md", "see [[Alice]] and [[Alice#intro]]")
    dst, updated = vault.move_note(tmp_path, "Alice.md", "People/Alicia.md")
    assert dst == tmp_path / "People" / "Alicia.md"
    assert updated == ["log.md"]
    assert vault.read_note(tmp_path, "log.md") == "see [[Alicia]] and [[Alicia#intro]]"
    assert not (tmp_path / "Alice.md").exists()


def test_move_refuses_existing_dst(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "a")
    vault.create_note(tmp_path, "b.md", "b")
    with pytest.raises(FileExistsError):
        vault.move_note(tmp_path, "a.md", "b.md")


def test_trash_soft_deletes(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "bye")
    dst = vault.trash_note(tmp_path, "a.md")
    assert dst == tmp_path / "_trash" / "a.md"
    assert dst.read_text(encoding="utf-8") == "bye"
    assert not (tmp_path / "a.md").exists()


def test_trash_collision_numbers(tmp_path: Path) -> None:
    vault.create_note(tmp_path, "a.md", "one")
    vault.trash_note(tmp_path, "a.md")
    vault.create_note(tmp_path, "a.md", "two")
    dst = vault.trash_note(tmp_path, "a.md")
    assert dst == tmp_path / "_trash" / "a_1.md"
