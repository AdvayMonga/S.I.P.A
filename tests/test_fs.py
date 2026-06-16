from pathlib import Path

import pytest
from servers.fs.server import resolve_within


def test_allows_path_inside_root(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hi")
    assert resolve_within(str(tmp_path / "a.txt"), [tmp_path]) == (tmp_path / "a.txt").resolve()


def test_allows_the_root_itself(tmp_path: Path) -> None:
    assert resolve_within(str(tmp_path), [tmp_path]) == tmp_path.resolve()


def test_denies_outside_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_within("/etc/passwd", [tmp_path])


def test_denies_traversal_escape(tmp_path: Path) -> None:
    # ../ that climbs out of the root must be rejected (resolved before the check).
    with pytest.raises(ValueError):
        resolve_within(str(tmp_path / ".." / "secret.txt"), [tmp_path])


def test_no_roots_denies_everything(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_within(str(tmp_path / "a.txt"), [])
