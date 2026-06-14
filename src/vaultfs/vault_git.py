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
