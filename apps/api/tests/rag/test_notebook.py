from app.rag.notebook import parse_notebook, slugify
from tests.rag.fixtures import NOTEBOOK, code, md


def test_chapter_and_sections_detected() -> None:
    chunks = parse_notebook(NOTEBOOK, 5)
    assert {c.chapter for c in chunks} == {"Conditionals and Recursion"}
    assert [c.section for c in chunks] == [
        "Introduction",
        "Boolean Expressions",
        "The `else` clause",
        "Glossary",
        "Exercises > Exercise",
        "Exercises > Exercise",
    ]


def test_boilerplate_is_dropped() -> None:
    text = "\n".join(c.content for c in parse_notebook(NOTEBOOK, 5))
    assert "Bookshop" not in text
    assert "download(" not in text
    assert "Colab" not in text
    assert "Copyright" not in text
    assert "%%expect" not in text


def test_code_cells_are_fenced() -> None:
    boolean = next(c for c in parse_notebook(NOTEBOOK, 5) if c.section == "Boolean Expressions")
    assert "```python\n5 == 5\n```" in boolean.content


def test_kinds() -> None:
    kinds = [c.kind for c in parse_notebook(NOTEBOOK, 5)]
    assert kinds == ["text", "text", "text", "glossary", "exercise", "exercise"]


def test_each_exercise_is_its_own_chunk() -> None:
    exercises = [c.content for c in parse_notebook(NOTEBOOK, 5) if c.kind == "exercise"]
    assert len(exercises) == 2
    assert "is_even" in exercises[0] and "sign" not in exercises[0]


def test_urls_point_at_the_online_book_section() -> None:
    chunk = next(c for c in parse_notebook(NOTEBOOK, 5) if c.section == "The `else` clause")
    assert (
        chunk.source_uri == "https://allendowney.github.io/ThinkPython/chap05.html#the-else-clause"
    )


def test_slugify() -> None:
    assert slugify("Stack diagrams for recursive functions") == (
        "stack-diagrams-for-recursive-functions"
    )
    assert slugify("The `else` clause") == "the-else-clause"


def test_long_sections_are_split_under_the_limit() -> None:
    paragraphs = [md("# T"), md("## Long")] + [md("word " * 60) for _ in range(20)]
    chunks = parse_notebook({"cells": paragraphs}, 1, max_chars=500)
    assert len(chunks) > 1
    assert all(len(c.content) <= 500 for c in chunks)


def test_a_single_huge_cell_is_split_on_lines() -> None:
    cells = [md("# T"), md("## S"), code("\n".join(f"x{i} = {i}" for i in range(200)))]
    chunks = parse_notebook({"cells": cells}, 1, max_chars=300)
    assert len(chunks) > 1
    assert all(len(c.content) <= 300 for c in chunks)


def test_text_is_nfc_normalised() -> None:
    decomposed = "Tiếng Việt"  # "Tiếng Việt" with combining marks
    chunks = parse_notebook({"cells": [md("# T"), md(decomposed)]}, 1)
    assert chunks[0].content == "Tiếng Việt"


def test_notebook_without_title_yields_nothing() -> None:
    assert parse_notebook({"cells": [md("just text")]}, 1) == []


def test_embedding_text_includes_headings() -> None:
    chunk = parse_notebook(NOTEBOOK, 5)[1]
    assert chunk.embedding_text.startswith("Conditionals and Recursion > Boolean Expressions")
