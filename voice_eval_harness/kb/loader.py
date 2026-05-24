"""Markdown knowledge-base loader.

v0.1 uses a simple, dependency-free header-based chunker so the base
package install doesn't drag in langchain. The chunker splits on ATX
headers (``#``, ``##``, ``###``) and emits one ``KbChunk`` per section.

A future upgrade can swap in ``langchain_text_splitters.MarkdownHeaderTextSplitter``
behind the same interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADER = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class KbChunk:
    source: str        # file path
    section: str       # header trail, e.g. "providers > stockton"
    text: str          # raw markdown body of the section
    chunk_id: str      # source:section


def _chunk_one_file(path: Path) -> list[KbChunk]:
    text = path.read_text()
    # Find all header positions; carve sections between them.
    headers: list[tuple[int, int, str]] = []
    for m in _HEADER.finditer(text):
        depth = len(m.group(1))
        title = m.group(2).strip()
        headers.append((m.start(), depth, title))

    if not headers:
        return [KbChunk(
            source=str(path),
            section=path.stem,
            text=text.strip(),
            chunk_id=f"{path}:0",
        )]

    chunks: list[KbChunk] = []
    section_stack: list[tuple[int, str]] = []
    for i, (start, depth, title) in enumerate(headers):
        # Trim the stack to keep only headers shallower than the current one.
        section_stack = [(d, t) for (d, t) in section_stack if d < depth]
        section_stack.append((depth, title))
        section_path = " > ".join(t for _, t in section_stack)

        body_start = start
        body_end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end].strip()
        # Skip empty or near-empty sections.
        if len(body.splitlines()) <= 1:
            continue
        chunks.append(KbChunk(
            source=str(path),
            section=section_path,
            text=body,
            chunk_id=f"{path}:{i}",
        ))
    return chunks


def load_kb(paths: list[Path]) -> list[KbChunk]:
    """Load every markdown file under ``paths`` (files or directories)."""
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.md")))
        elif p.is_file():
            files.append(p)
    chunks: list[KbChunk] = []
    for f in files:
        chunks.extend(_chunk_one_file(f))
    return chunks


def load_kb_glob(pattern: str, base: Path | None = None) -> list[KbChunk]:
    """Glob a pattern (relative to ``base`` or cwd) and load matching files."""
    base = base or Path.cwd()
    matches = sorted(base.glob(pattern))
    return load_kb(matches)
