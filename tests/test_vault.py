from pathlib import Path

import pytest

from bot.servers.obsidian.vault import create_note


def test_create_writes_file(tmp_path: Path) -> None:
    note = create_note(tmp_path, "notes/hello.md", "# Hello")
    assert note == tmp_path / "notes" / "hello.md"
    assert note.read_text(encoding="utf-8") == "# Hello"


def test_create_refuses_overwrite(tmp_path: Path) -> None:
    create_note(tmp_path, "a.md", "first")
    with pytest.raises(FileExistsError):
        create_note(tmp_path, "a.md", "second")
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "first"


def test_path_traversal_blocked(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_note(tmp_path, "../escape.md", "nope")
    assert not (tmp_path.parent / "escape.md").exists()


def test_extension_whitelist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_note(tmp_path, "note.txt", "nope")
