"""Heading-aware chunking of notes for embedding."""

import re
from dataclasses import dataclass

import frontmatter

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


@dataclass
class Chunk:
    path: str
    heading: str
    text: str


def chunk_note(rel_path: str, raw: str) -> list[Chunk]:
    """Split a note into chunks by heading (frontmatter stripped). Empty chunks dropped."""
    body = frontmatter.loads(raw).content
    segments: list[tuple[str, list[str]]] = []
    heading = ""
    lines: list[str] = []
    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            segments.append((heading, lines))
            heading = match.group(2).strip()
            lines = [line]
        else:
            lines.append(line)
    segments.append((heading, lines))

    chunks: list[Chunk] = []
    for head, seg_lines in segments:
        text = "\n".join(seg_lines).strip()
        if text:
            chunks.append(Chunk(path=rel_path, heading=head, text=text))
    return chunks
