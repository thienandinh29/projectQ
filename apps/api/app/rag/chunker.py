"""Generic chunker: a `ParsedDocument` (what P3's readers emit) becomes citable `Chunk`s.

Contract: `app/schemas.py` `ParsedDocument` / `DocBlock`. Readers (HTML, PDF, DOCX, link) only emit
blocks in reading order; everything about chunk size and boundaries lives here, so every source is
chunked alike.

Guarantees, all tested:
  - No chunk is longer than `max_chars`. The embedding server truncates what is too long, silently,
    so an oversized chunk would hide its tail from retrieval.
  - A chunk never mixes sections, kinds, source URIs or pages, so a citation always points at the
    right place and the right PDF page.
  - No text is lost or reordered; code indentation survives.
  - Text is NFC-normalised (Vietnamese), blank blocks are dropped, output is deterministic.

Splitting goes from the coarsest boundary to the finest: paragraphs, lines, sentences, words, and
only for an unbroken run (a long URL) a hard cut.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence

from app.rag.notebook import MAX_CHARS, Chunk
from app.schemas import DocBlock, ParsedDocument

# (pattern separating the pieces, joiner used when pieces are packed back together)
_LEVELS = (
    (re.compile(r"\n[ \t]*\n"), "\n\n"),  # blank line; does not eat the next line's indentation
    (re.compile(r"\n"), "\n"),
    (re.compile(r"(?<=[.!?…])\s+"), " "),
    (re.compile(r"\s+"), " "),
)


def split_text(text: str, limit: int) -> list[str]:
    """Cut `text` into pieces of at most `limit` characters at the coarsest boundaries that fit."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    text = text.strip()
    return _split(text, limit, 0) if text else []


def _split(text: str, limit: int, level: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    if level == len(_LEVELS):
        return [text[i : i + limit] for i in range(0, len(text), limit)]
    pattern, joiner = _LEVELS[level]
    pieces = [p.rstrip() for p in pattern.split(text) if p.strip()]
    if len(pieces) <= 1:
        return _split(text, limit, level + 1)

    out: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > limit:
            if current:
                out.append(current)
                current = ""
            out.extend(_split(piece, limit, level + 1))
            continue
        candidate = f"{current}{joiner}{piece}" if current else piece
        if len(candidate) > limit:
            out.append(current)
            current = piece
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def pack(texts: Iterable[str], limit: int) -> list[str]:
    """Join consecutive texts (blank line between) into chunks of at most `limit` characters."""
    chunks: list[str] = []
    current = ""
    for text in texts:
        for piece in split_text(unicodedata.normalize("NFC", text), limit):
            candidate = f"{current}\n\n{piece}" if current else piece
            if len(candidate) > limit:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_document(doc: ParsedDocument, *, max_chars: int = MAX_CHARS) -> list[Chunk]:
    """Chunks in reading order; consecutive blocks with the same location are packed together."""
    chunks: list[Chunk] = []
    for group in _groups(doc.blocks):
        first = group[0]
        chapter = unicodedata.normalize("NFC", first.chapter).strip()
        section = unicodedata.normalize("NFC", first.section).strip()
        for content in pack((b.text for b in group), max_chars):
            chunks.append(
                Chunk(
                    chapter_no=first.chapter_no,
                    chapter=chapter,
                    section=section,
                    kind=first.kind,
                    content=content,
                    source_uri=first.source_uri,
                    page=first.page,
                )
            )
    return chunks


def _location(block: DocBlock) -> tuple[object, ...]:
    return (
        block.chapter_no,
        block.chapter,
        block.section,
        block.kind,
        block.source_uri,
        block.page,
    )


def _groups(blocks: Sequence[DocBlock]) -> list[list[DocBlock]]:
    """Consecutive blocks that share a location (never merged across a change of it)."""
    groups: list[list[DocBlock]] = []
    for block in blocks:
        if groups and _location(groups[-1][0]) == _location(block):
            groups[-1].append(block)
        else:
            groups.append([block])
    return groups
