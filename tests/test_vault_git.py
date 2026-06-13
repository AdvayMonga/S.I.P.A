import subprocess
from pathlib import Path

from bot.servers.obsidian import vault_git


def _log(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "log", "--pretty=%s"], cwd=root, capture_output=True, text=True
    )
    return out.stdout.splitlines()


def test_commit_inits_and_records(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("hello", encoding="utf-8")
    rev = vault_git.commit(tmp_path, "create a.md")
    assert rev is not None
    assert (tmp_path / ".git").is_dir()
    assert _log(tmp_path) == ["create a.md"]


def test_commit_noop_when_clean(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("hello", encoding="utf-8")
    vault_git.commit(tmp_path, "first")
    assert vault_git.commit(tmp_path, "second") is None
    assert _log(tmp_path) == ["first"]
