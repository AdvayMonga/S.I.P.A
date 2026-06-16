"""Local-only git for the vault: init on demand, auto-commit per mutation. Never pushed."""

import subprocess
from pathlib import Path

_IDENT = ["-c", "user.name=S.I.P.A.", "-c", "user.email=sipa@localhost"]


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def ensure_repo(vault_root: str | Path) -> None:
    root = Path(vault_root)
    if (root / ".git").is_dir():
        return
    result = _git(["init", "-q"], root)
    if result.returncode != 0:
        raise RuntimeError(f"git init failed: {result.stderr.strip()}")


def commit(vault_root: str | Path, message: str) -> str | None:
    """Stage all vault changes and commit. Returns the short hash, or None if nothing changed."""
    root = Path(vault_root)
    ensure_repo(root)
    _git(["add", "-A"], root)
    if _git(["diff", "--cached", "--quiet"], root).returncode == 0:
        return None  # nothing staged
    result = _git([*_IDENT, "commit", "-q", "-m", message], root)
    if result.returncode != 0:
        raise RuntimeError(f"git commit failed: {result.stderr.strip()}")
    return _git(["rev-parse", "--short", "HEAD"], root).stdout.strip() or None


def undo_last(vault_root: str | Path) -> str | None:
    """Revert the most recent S.I.P.A. change (a new commit undoing HEAD). Returns the undone
    commit's subject, or None if there's nothing safe to undo (no prior commit, or HEAD is the
    user's own/baseline edit — we only undo our own changes)."""
    root = Path(vault_root)
    if not (root / ".git").is_dir():
        return None
    count = _git(["rev-list", "--count", "HEAD"], root).stdout.strip()
    if not count.isdigit() or int(count) < 2:  # can't revert the baseline/root commit
        return None
    if _git(["log", "-1", "--format=%an"], root).stdout.strip() != "S.I.P.A.":
        return None  # last change wasn't ours — leave the user's edits alone
    subject = _git(["log", "-1", "--format=%s"], root).stdout.strip()
    result = _git([*_IDENT, "revert", "--no-edit", "HEAD"], root)
    if result.returncode != 0:
        raise RuntimeError(f"git revert failed: {result.stderr.strip()}")
    return subject
