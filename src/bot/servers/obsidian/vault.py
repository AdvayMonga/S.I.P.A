"""Path-safe, atomic note writes into the vault. No git yet (see PLAN.md / DECISIONS.md)."""

import os
import tempfile
from pathlib import Path

ALLOWED_SUFFIXES = {".md"}


def _safe_target(vault_root: Path, rel_path: str) -> Path:
    """Resolve `rel_path` to a path confined inside the vault, with a suffix allowlist."""
    rel = Path(rel_path)
    if rel.is_absolute():
        raise ValueError("path must be relative to the vault root")
    if rel.suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported file type: {rel.suffix or '(none)'}")
    root = vault_root.resolve()
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path escapes the vault root")
    return target


def _atomic_write(target: Path, content: str) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def create_note(vault_root: str | Path, rel_path: str, content: str) -> Path:
    """Create a new note. Fails if it already exists. Returns the absolute path."""
    target = _safe_target(Path(vault_root), rel_path)
    if target.exists():
        raise FileExistsError(f"note already exists: {rel_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, content)
    return target
