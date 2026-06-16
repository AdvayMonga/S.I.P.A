import subprocess
from pathlib import Path

from vaultfs import vault_git


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


def test_undo_reverts_last_change(tmp_path: Path) -> None:
    note = tmp_path / "a.md"
    note.write_text("v1", encoding="utf-8")
    vault_git.commit(tmp_path, "create a.md")
    note.write_text("v2", encoding="utf-8")
    vault_git.commit(tmp_path, "edit a.md")

    subject = vault_git.undo_last(tmp_path)
    assert subject == "edit a.md"
    assert note.read_text(encoding="utf-8") == "v1"  # reverted on disk
    assert _log(tmp_path)[0].startswith("Revert")  # history preserved


def test_undo_refuses_when_only_baseline(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("only", encoding="utf-8")
    vault_git.commit(tmp_path, "baseline")
    assert vault_git.undo_last(tmp_path) is None  # nothing prior to revert to


def test_undo_leaves_user_commits_alone(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    vault_git.commit(tmp_path, "sipa change")
    # a non-S.I.P.A. (user) commit on top
    (tmp_path / "b.md").write_text("y", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path)
    subprocess.run(
        ["git", "-c", "user.name=Advay", "-c", "user.email=a@b.c", "commit", "-q", "-m", "my edit"],
        cwd=tmp_path,
    )
    assert vault_git.undo_last(tmp_path) is None  # won't touch the user's own commit
