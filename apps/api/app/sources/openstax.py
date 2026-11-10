"""OpenStax books from their git repositories: pure parsers, no network (see `fetch.py`).

An OpenStax book repository holds `collections/<slug>.collection.xml` (title, licence URL, the
chapter tree) and `modules/<id>/index.cnxml` (one page per module). Both are XML with stable
namespaces, so the licence and the chapter order are read, never inferred.

Output follows the existing library contract: `DocBlock`s in reading order, one block per
section, with `source_uri` pointing at the module file pinned to the commit. Learning objectives
are kept separately (`outline.json`) because Deep Research matches topics against them.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from app.sources.licence import licence_from_url

COL = "{http://cnx.rice.edu/collxml}"
MD = "{http://cnx.rice.edu/mdml}"
CNX = "{http://cnx.rice.edu/cnxml}"
MATH = "{http://www.w3.org/1998/Math/MathML}"

_SKIP = {"media", "image", "iframe", "metadata", "title", "label"}


@dataclass(frozen=True)
class Chapter:
    number: int  # 1-based, in reading order
    title: str
    unit: str | None  # the enclosing unit, when the book groups chapters into units
    modules: tuple[str, ...]


@dataclass(frozen=True)
class Collection:
    slug: str
    title: str
    language: str
    licence: str  # e.g. "CC BY-NC-SA 4.0"; ND and unknown licences raise LicenceError
    licence_url: str
    chapters: tuple[Chapter, ...]
    front_matter: tuple[str, ...]  # modules outside any chapter (preface, appendices)


@dataclass(frozen=True)
class Block:
    chapter_no: int
    chapter: str
    section: str
    kind: str  # "text" | "exercise" | "glossary" (the library contract)
    text: str
    source_uri: str

    def to_contract(self) -> dict[str, object]:
        return {
            "chapter_no": self.chapter_no,
            "chapter": self.chapter,
            "section": self.section,
            "kind": self.kind,
            "text": self.text,
            "source_uri": self.source_uri,
        }


@dataclass
class Page:
    module: str
    title: str
    source_uri: str
    blocks: list[Block] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


_BREAK = "\x00"  # an explicit <newline/>; source line breaks are just whitespace


def _squash(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split(_BREAK)]
    return "\n".join(line for line in lines if line)


# --- MathML -------------------------------------------------------------------------------------
# Formulas are linearised to readable text (a/b, x^2, x_i, sqrt(x)). This loses layout but keeps the
# content searchable and quotable, which flattening the raw MathML text would not (it glues tokens).


def _math(node: ET.Element) -> str:
    tag = _local(node.tag)
    kids = list(node)
    parts = [_math(k) for k in kids]
    if tag in {"mi", "mn", "mo", "mtext", "ms"}:
        return (node.text or "").strip()
    if tag == "mspace":
        return " "
    if tag == "mfrac" and len(parts) == 2:
        return f"({parts[0]})/({parts[1]})"
    if tag == "msup" and len(parts) == 2:
        return f"{parts[0]}^{_group(parts[1])}"
    if tag == "msub" and len(parts) == 2:
        return f"{parts[0]}_{_group(parts[1])}"
    if tag == "msubsup" and len(parts) == 3:
        return f"{parts[0]}_{_group(parts[1])}^{_group(parts[2])}"
    if tag == "msqrt":
        return f"sqrt({''.join(parts)})"
    if tag == "mroot" and len(parts) == 2:
        return f"root{_group(parts[1])}({parts[0]})"
    if tag == "mover" and len(parts) == 2:
        accent = parts[1]
        if accent in {"¯", "‾", "-", "―", "_"}:
            return f"{parts[0]}̄"  # x̄
        if accent in {"^", "\u02c6"}:  # caret or modifier circumflex
            return f"{parts[0]}̂"  # p̂
        return f"{parts[0]}^{_group(accent)}"
    if tag == "munder" and len(parts) == 2:
        return f"{parts[0]}_{_group(parts[1])}"
    if tag == "munderover" and len(parts) == 3:
        return f"{parts[0]}_{_group(parts[1])}^{_group(parts[2])}"
    if tag == "mtr":
        return " | ".join(parts)
    if tag == "mtable":
        return "; ".join(parts)
    if tag == "annotation" or tag == "annotation-xml":
        return ""
    return "".join(parts)


def _group(text: str) -> str:
    return text if len(text) <= 1 else f"({text})"


# --- CNXML text ---------------------------------------------------------------------------------


def _inline(node: ET.Element) -> str:
    """Text of an element, with inline code, links, math and line breaks handled."""
    out: list[str] = [node.text or ""]
    for child in node:
        tag = _local(child.tag)
        if child.tag.startswith(MATH):
            out.append(f" {_math(child)} " if tag == "math" else _math(child))
        elif tag == "newline":
            out.append(_BREAK)
        elif tag in _SKIP:
            pass
        elif tag == "sup":
            out.append("^" + _inline(child))
        elif tag == "sub":
            out.append("_" + _inline(child))
        else:
            out.append(_inline(child))
        out.append(child.tail or "")
    return "".join(out)


def _text(node: ET.Element) -> str:
    return _squash(_inline(node))


def _title(node: ET.Element) -> str:
    title = node.find(f"{CNX}title")
    return _text(title) if title is not None else ""


def _code_block(node: ET.Element) -> str:
    return "```\n" + "".join(node.itertext()).strip("\n") + "\n```"


def _table(node: ET.Element) -> str:
    rows = []
    for row in node.iter(f"{CNX}row"):
        rows.append(" | ".join(_text(entry) for entry in row.findall(f"{CNX}entry")))
    caption = _title(node)
    return "\n".join(([caption] if caption else []) + rows)


def _list(node: ET.Element) -> str:
    return "\n".join("- " + _text(item) for item in node.findall(f"{CNX}item"))


def _exercise(node: ET.Element) -> str:
    """Problem and solutions as text; "" when the problem has no text of its own (for example an
    embedded interactive exercise that lives outside the repository)."""
    problem = node.find(f"{CNX}problem")
    body = _flow(problem) if problem is not None else ""
    if not body:
        return ""
    parts = ["Problem: " + body]
    for solution in node.findall(f"{CNX}solution"):
        answer = _flow(solution)
        if answer:
            parts.append("Solution: " + answer)
    return "\n\n".join(parts)


def _flow(node: ET.Element) -> str:
    """Block-level content of an element as paragraphs (no section splitting)."""
    parts: list[str] = []
    if (node.text or "").strip():
        parts.append(_squash(node.text or ""))
    for child in node:
        tag = _local(child.tag)
        if tag in _SKIP:
            pass
        elif tag == "code" and child.get("display") == "block":
            parts.append(_code_block(child))
        elif tag == "list":
            parts.append(_list(child))
        elif tag == "table":
            parts.append(_table(child))
        elif tag == "figure":
            caption = child.find(f"{CNX}caption")
            if caption is not None and _text(caption):
                parts.append("Figure: " + _text(caption))
        elif tag in {"para", "note", "example", "equation", "quote", "definition", "problem"}:
            heading = _title(child) if tag in {"note", "example"} else ""
            body = _flow(child) if tag in {"note", "example", "quote"} else _text(child)
            if body:
                parts.append(f"{heading}: {body}" if heading else body)
        elif tag == "exercise":
            parts.append(_exercise(child))
        else:
            text = _text(child)
            if text:
                parts.append(text)
        if (child.tail or "").strip():
            parts.append(_squash(child.tail or ""))
    return "\n\n".join(p for p in parts if p)


def parse_module(
    xml: bytes | str, *, module: str, chapter_no: int, chapter: str, source_uri: str
) -> Page:
    """One CNXML page -> blocks (one per section, exercises separate) and learning objectives."""
    root = ET.fromstring(xml)
    title = _title(root) or module
    page = Page(module=module, title=title, source_uri=source_uri)
    content = root.find(f"{CNX}content")
    if content is None:
        return page
    parents = {child: parent for parent in content.iter() for child in parent}

    def section_of(node: ET.Element) -> tuple[str, str | None]:
        current = parents.get(node)
        while current is not None and _local(current.tag) != "section":
            current = parents.get(current)
        if current is None:
            return title, None
        return f"{title}: {_title(current) or title}", current.get("id")

    # Exercises can sit inside notes or examples: lift each outermost one into its own block, so
    # text blocks stay prose and exercises can later seed items. Objectives notes are read, kept.
    lifted: list[tuple[ET.Element, str, str | None]] = []
    for node in list(content.iter(f"{CNX}exercise")):
        ancestor, nested = parents.get(node), False
        while ancestor is not None:
            if _local(ancestor.tag) == "exercise":
                nested = True
                break
            ancestor = parents.get(ancestor)
        if not nested:
            section, anchor = section_of(node)
            lifted.append((node, section, node.get("id") or anchor))
    for node, _, _ in lifted:
        parent = parents.get(node)
        if parent is not None:
            parent.remove(node)
    for note in content.iter(f"{CNX}note"):
        if "objective" in (note.get("class") or ""):
            page.objectives.extend(_text(i) for i in note.iter(f"{CNX}item") if _text(i))

    def emit(section: str, anchor: str | None, kind: str, text: str) -> None:
        if text.strip():
            uri = f"{source_uri}#{anchor}" if anchor else source_uri
            page.blocks.append(Block(chapter_no, chapter, section, kind, text.strip(), uri))

    def walk(node: ET.Element, section: str, anchor: str | None) -> None:
        parts: list[str] = []

        def flush() -> None:
            emit(section, anchor, "text", "\n\n".join(p for p in parts if p))
            parts.clear()

        for child in node:
            tag = _local(child.tag)
            if tag == "section":
                flush()
                name = _title(child) or section
                if name.casefold().startswith("learning objective"):
                    lists = child.findall(f".//{CNX}list")
                    page.objectives.extend(
                        _text(i) for lst in lists for i in lst.findall(f"{CNX}item") if _text(i)
                    )
                walk(child, f"{title}: {name}", child.get("id"))
            elif tag == "exercise":
                emit(section, child.get("id") or anchor, "exercise", _exercise(child))
            elif tag in _SKIP:
                continue
            else:
                wrapper = ET.Element(node.tag)
                wrapper.append(child)
                text = _flow(wrapper)
                if text:
                    parts.append(text)
        flush()

    walk(content, title, None)
    for node, section, anchor in lifted:
        emit(section, anchor, "exercise", _exercise(node))
    glossary = root.find(f"{CNX}glossary")
    if glossary is not None:
        terms = []
        for definition in glossary.findall(f"{CNX}definition"):
            term, meaning = definition.find(f"{CNX}term"), definition.find(f"{CNX}meaning")
            if term is not None and meaning is not None:
                terms.append(f"**{_text(term)}:** {_text(meaning)}")
        emit(f"{title}: Glossary", None, "glossary", "\n".join(terms))
    return page


def parse_collection(xml: bytes | str) -> Collection:
    """The book's metadata and chapter tree. Raises `LicenceError` for ND or unknown licences."""
    root = ET.fromstring(xml)
    meta = root.find(f"{COL}metadata")
    content = root.find(f"{COL}content")
    if meta is None or content is None:
        raise ValueError("not an OpenStax collection: metadata or content is missing")

    def md(name: str) -> str:
        el = meta.find(f"{MD}{name}")
        return (el.text or "").strip() if el is not None else ""

    licence_el = meta.find(f"{MD}license")
    licence_url = licence_el.get("url", "") if licence_el is not None else ""
    licence = licence_from_url(licence_url)

    chapters: list[Chapter] = []
    loose: list[str] = [m.get("document", "") for m in content.findall(f"{COL}module")]

    def visit(sub: ET.Element, unit: str | None) -> None:
        title_el = sub.find(f"{MD}title")
        title = (title_el.text or "").strip() if title_el is not None else ""
        inner = sub.find(f"{COL}content")
        if inner is None:
            return
        nested = inner.findall(f"{COL}subcollection")
        modules = tuple(m.get("document", "") for m in inner.findall(f"{COL}module"))
        if nested and not modules:  # a unit that groups chapters
            for child in nested:
                visit(child, title)
            return
        chapters.append(Chapter(len(chapters) + 1, title, unit, modules))
        for child in nested:  # rare: a chapter with sub-groups; keep their pages in order
            deeper = child.find(f"{COL}content")
            if deeper is not None:
                extra = tuple(m.get("document", "") for m in deeper.iter(f"{COL}module"))
                last = chapters[-1]
                chapters[-1] = Chapter(last.number, last.title, last.unit, last.modules + extra)

    for sub in content.findall(f"{COL}subcollection"):
        visit(sub, None)
    if not chapters:
        raise ValueError("the collection has no chapters")
    return Collection(
        slug=md("slug"),
        title=md("title"),
        language=md("language") or "en",
        licence=licence,
        licence_url=licence_url,
        chapters=tuple(chapters),
        front_matter=tuple(m for m in loose if m),
    )
