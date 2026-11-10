"""Turn a Think Python chapter notebook (.ipynb JSON) into citable chunks.

Pure: takes the parsed notebook dict, returns chunks. No I/O, so it is tested with small fixtures.
Layout of the book's notebooks:
  "# Title" = chapter, "## Heading" = section, "### Exercise" = one exercise,
  "## Glossary" = term definitions. Cells before the chapter title (shop links, download
  helpers), the Colab link and the trailing copyright cell are not book content.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

ChunkKind = Literal["text", "exercise", "glossary"]

BOOK_URL = "https://allendowney.github.io/ThinkPython"
MAX_CHARS = 1800  # ~400 tokens: big enough for a code example plus its explanation


@dataclass(frozen=True)
class Chunk:
    chapter_no: int | None
    chapter: str
    section: str
    kind: ChunkKind
    content: str
    source_uri: str  # web URL of the section, or the storage path of an upload (chunks.source_uri)
    page: int | None = None  # 1-based PDF page; None for web sources (chunks.page)

    @property
    def embedding_text(self) -> str:
        # Headings give the embedding model context a bare paragraph lacks.
        return f"{self.chapter} > {self.section}\n\n{self.content}"


def slugify(heading: str) -> str:
    """Approximate Jupyter Book's heading anchors: 'The `else` clause' -> 'the-else-clause'."""
    text = heading.replace("`", "").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _source(cell: dict[str, Any]) -> str:
    src = cell.get("source", "")
    text = "".join(src) if isinstance(src, list) else str(src)
    return unicodedata.normalize("NFC", text).strip()


def _is_boilerplate(cell_type: str, text: str) -> bool:
    if not text:
        return True
    if cell_type == "markdown":
        return text.startswith("[Run this notebook on Colab]") or "Code license:" in text
    # Notebook plumbing, not Python the book teaches.
    first = text.splitlines()[0]
    return first.startswith(("%", "!")) or "download(" in text


def _render(cell_type: str, text: str) -> str:
    return f"```python\n{text}\n```" if cell_type == "code" else text


def _split_long(text: str, limit: int) -> list[str]:
    """Split one oversized cell on line boundaries."""
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            parts.append(current.rstrip())
            current = ""
        current += line
    if current.strip():
        parts.append(current.rstrip())
    return parts


def _pack(blocks: list[str], limit: int) -> list[str]:
    """Greedily join consecutive blocks into chunks of at most ~limit chars."""
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for block in blocks:
        pieces = _split_long(block, limit) if len(block) > limit else [block]
        for piece in pieces:
            if current and size + len(piece) > limit:
                chunks.append("\n\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _kind_for(section: str, subsection: str | None) -> ChunkKind:
    if section.lower() == "glossary":
        return "glossary"
    if subsection is not None and subsection.lower().startswith("exercise"):
        return "exercise"
    return "text"


def parse_notebook(
    notebook: dict[str, Any], chapter_no: int, *, max_chars: int = MAX_CHARS
) -> list[Chunk]:
    chapter: str | None = None
    section = "Introduction"
    subsection: str | None = None
    groups: list[tuple[str, str | None, list[str]]] = []  # (section, subsection, blocks)

    for cell in notebook.get("cells", []):
        cell_type = str(cell.get("cell_type", ""))
        text = _source(cell)
        if cell_type == "markdown" and text.startswith("# "):
            chapter = text.splitlines()[0][2:].strip()
            continue
        if chapter is None or _is_boilerplate(cell_type, text):
            continue
        if cell_type == "markdown" and text.startswith("## "):
            heading, _, rest = text.partition("\n")
            section, subsection = heading[3:].strip(), None
            groups.append((section, subsection, []))
            text = rest.strip()
        elif cell_type == "markdown" and text.startswith("### "):
            heading, _, rest = text.partition("\n")
            subsection = heading[4:].strip()
            # Each exercise is its own group so a chunk never mixes two exercises.
            groups.append((section, subsection, []))
            text = rest.strip()
        if not groups:
            groups.append((section, subsection, []))
        if text:
            groups[-1][2].append(_render(cell_type, text))

    if chapter is None:
        return []

    chunks: list[Chunk] = []
    page = f"{BOOK_URL}/chap{chapter_no:02d}.html"
    for sec, sub, blocks in groups:
        if not blocks:
            continue
        label = f"{sec} > {sub}" if sub else sec
        url = f"{page}#{slugify(sec)}"
        for content in _pack(blocks, max_chars):
            chunks.append(
                Chunk(
                    chapter_no=chapter_no,
                    chapter=chapter,
                    section=label,
                    kind=_kind_for(sec, sub),
                    content=content,
                    source_uri=url,
                )
            )
    return chunks
