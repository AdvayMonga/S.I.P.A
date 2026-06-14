"""Vault filesystem ops: path-safe reads and atomic, validated writes. No git, no MCP here."""

import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import frontmatter

ALLOWED_SUFFIXES = {".md"}
TRASH_DIR = "_trash"
INTERNAL_DIRS = {"_trash", "_system"}  # bot-internal; excluded from listing/search/index

_WIKILINK = re.compile(r"\[\[([^\]|#\n]+)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


# --- path safety --------------------------------------------------------------


def _safe_target(vault_root: Path, rel_path: str) -> Path:
    """Resolve a note path confined to the vault, with a suffix allowlist."""
    rel = Path(rel_path)
    if rel.is_absolute():
        raise ValueError("path must be relative to the vault root")
    if rel.suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"unsupported file type: {rel.suffix or '(none)'}")
    return _confine(vault_root.resolve(), rel)


def _safe_dir(vault_root: Path, folder: str) -> Path:
    rel = Path(folder)
    if rel.is_absolute():
        raise ValueError("folder must be relative to the vault root")
    return _confine(vault_root.resolve(), rel)


def _confine(root: Path, rel: Path) -> Path:
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


def _iter_notes(root: Path, base: Path) -> Iterator[Path]:
    """Yield `*.md` under `base`, excluding the vault's internal trees (`_trash`, `_system`)."""
    internal = {(root / name).resolve() for name in INTERNAL_DIRS}
    for path in sorted(base.rglob("*.md")):
        resolved = path.resolve()
        if any(resolved == d or d in resolved.parents for d in internal):
            continue
        yield path


# --- validation ---------------------------------------------------------------


def validate_markdown(content: str) -> None:
    """Reject malformed frontmatter before it lands. (Table checks: see BACKLOG.md.)"""
    try:
        frontmatter.loads(content)
    except Exception as exc:  # surface any parse failure as a rejection
        raise ValueError(f"invalid frontmatter: {exc}") from exc


def unresolved_links(vault_root: str | Path, content: str) -> list[str]:
    """Wikilink targets in `content` that don't resolve to a note (flagged, not rejected)."""
    root = Path(vault_root)
    titles = {m.group(1).strip() for m in _WIKILINK.finditer(content)}
    return sorted(t for t in titles if t and resolve_link(root, t) is None)


# --- reads --------------------------------------------------------------------


def read_note(vault_root: str | Path, rel_path: str) -> str:
    target = _safe_target(Path(vault_root), rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"no such note: {rel_path}")
    return target.read_text(encoding="utf-8")


def list_notes(vault_root: str | Path, folder: str | None = None) -> list[str]:
    root = Path(vault_root).resolve()
    base = _safe_dir(root, folder) if folder else root
    return [str(p.relative_to(root)) for p in _iter_notes(root, base)]


def search_text(
    vault_root: str | Path, query: str, limit: int = 20, regex: bool = False
) -> list[dict[str, Any]]:
    root = Path(vault_root).resolve()
    pattern = re.compile(query if regex else re.escape(query), re.IGNORECASE)
    hits: list[dict[str, Any]] = []
    for path in _iter_notes(root, root):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                hits.append(
                    {"path": str(path.relative_to(root)), "line": line_no, "text": line.strip()}
                )
                if len(hits) >= limit:
                    return hits
    return hits


def resolve_link(vault_root: str | Path, title: str) -> str | None:
    root = Path(vault_root).resolve()
    want = title.strip().lower()
    for path in _iter_notes(root, root):
        if path.stem.lower() == want:
            return str(path.relative_to(root))
    return None


def get_backlinks(vault_root: str | Path, rel_path: str) -> list[str]:
    root = Path(vault_root).resolve()
    target = _safe_target(root, rel_path)
    link = re.compile(r"\[\[\s*" + re.escape(target.stem) + r"\s*(?=[\]|#])")
    out: list[str] = []
    for path in _iter_notes(root, root):
        if path.resolve() == target:
            continue
        if link.search(path.read_text(encoding="utf-8")):
            out.append(str(path.relative_to(root)))
    return out


# --- writes -------------------------------------------------------------------


def _with_frontmatter(content: str, fm: dict[str, Any] | None) -> str:
    if not fm:
        return content
    return frontmatter.dumps(frontmatter.Post(content, **fm))


def create_note(
    vault_root: str | Path,
    rel_path: str,
    content: str,
    frontmatter_data: dict[str, Any] | None = None,
) -> Path:
    """Create a new note. Fails if it already exists. Returns the absolute path."""
    target = _safe_target(Path(vault_root), rel_path)
    if target.exists():
        raise FileExistsError(f"note already exists: {rel_path}")
    final = _with_frontmatter(content, frontmatter_data)
    validate_markdown(final)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, final)
    return target


def _find_heading(lines: list[str], heading: str) -> tuple[int | None, int]:
    want = heading.strip().lstrip("#").strip().lower()
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if match and match.group(2).strip().lower() == want:
            return index, len(match.group(1))
    return None, 0


def _section_end(lines: list[str], start: int, level: int) -> int:
    for index in range(start + 1, len(lines)):
        match = _HEADING.match(lines[index])
        if match and len(match.group(1)) <= level:
            return index
    return len(lines)


def append_note(
    vault_root: str | Path, rel_path: str, content: str, under_heading: str | None = None
) -> Path:
    """Non-destructively add `content` at the end of a section (or the file)."""
    target = _safe_target(Path(vault_root), rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"no such note: {rel_path}")
    existing = target.read_text(encoding="utf-8")
    block = content if content.endswith("\n") else content + "\n"

    if under_heading is None:
        sep = "" if existing == "" or existing.endswith("\n") else "\n"
        new = existing + sep + block
    else:
        lines = existing.splitlines(keepends=True)
        index, level = _find_heading(lines, under_heading)
        if index is None:
            raise ValueError(f"heading not found: {under_heading}")
        end = _section_end(lines, index, level)
        new = "".join(lines[:end]) + block + "".join(lines[end:])

    validate_markdown(new)
    _atomic_write(target, new)
    return target


def patch_section(vault_root: str | Path, rel_path: str, heading: str, content: str) -> Path:
    """Replace the body under `heading` (keeping the heading line). Heading must exist."""
    target = _safe_target(Path(vault_root), rel_path)
    if not target.is_file():
        raise FileNotFoundError(f"no such note: {rel_path}")
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    index, level = _find_heading(lines, heading)
    if index is None:
        raise ValueError(f"heading not found: {heading}")
    end = _section_end(lines, index, level)
    body = content if content.endswith("\n") else content + "\n"
    new = "".join(lines[: index + 1]) + body + "".join(lines[end:])
    validate_markdown(new)
    _atomic_write(target, new)
    return target


def _rewrite_links(root: Path, old_stem: str, new_stem: str) -> list[str]:
    if old_stem == new_stem:
        return []
    pattern = re.compile(r"(\[\[\s*)" + re.escape(old_stem) + r"(?=[\]|#])")
    updated: list[str] = []
    for path in _iter_notes(root, root):
        text = path.read_text(encoding="utf-8")
        new_text, count = pattern.subn(lambda m: m.group(1) + new_stem, text)
        if count:
            _atomic_write(path, new_text)
            updated.append(str(path.relative_to(root)))
    return updated


def move_note(vault_root: str | Path, old: str, new: str) -> tuple[Path, list[str]]:
    """Rename a note and best-effort rewrite inbound `[[stem]]` links. Returns (dst, updated)."""
    root = Path(vault_root).resolve()
    src = _safe_target(root, old)
    dst = _safe_target(root, new)
    if not src.is_file():
        raise FileNotFoundError(f"no such note: {old}")
    if dst.exists():
        raise FileExistsError(f"destination exists: {new}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)
    updated = _rewrite_links(root, src.stem, dst.stem)
    return dst, updated


def trash_note(vault_root: str | Path, rel_path: str) -> Path:
    """Soft-delete a note into `/_trash`, numbering on collision. No hard delete."""
    root = Path(vault_root).resolve()
    src = _safe_target(root, rel_path)
    if not src.is_file():
        raise FileNotFoundError(f"no such note: {rel_path}")
    base = root / TRASH_DIR / rel_path
    dst = base
    counter = 1
    while dst.exists():
        dst = base.with_name(f"{base.stem}_{counter}{base.suffix}")
        counter += 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)
    return dst
