from pathlib import Path

import pytest

from app.rag.library import load_book
from app.sources.fetch import CatalogBook, build_openstax
from app.sources.licence import LicenceError
from app.sources.openstax import parse_collection, parse_module
from tests.sources.fixtures import COLLECTION, MODULE, ND_COLLECTION, OBJECTIVES_NOTE_MODULE

URI = "https://github.com/o/r/blob/abc/modules/m1/index.cnxml"


def test_collection_reads_licence_and_chapter_order_from_metadata() -> None:
    book = parse_collection(COLLECTION)
    assert (book.slug, book.title, book.licence) == ("tiny-book", "Tiny Book", "CC BY 4.0")
    assert [(c.number, c.title, c.unit, c.modules) for c in book.chapters] == [
        (1, "Loops", "Unit One", ("m1", "m2")),
        (2, "Functions", None, ("m3",)),
    ]
    assert book.front_matter == ("m0",)


def test_collection_with_no_derivatives_licence_is_refused() -> None:
    with pytest.raises(LicenceError):
        parse_collection(ND_COLLECTION)


def test_module_blocks_objectives_math_code_and_exercises() -> None:
    page = parse_module(MODULE, module="m1", chapter_no=1, chapter="Loops", source_uri=URI)
    assert page.title == "While loops"
    assert page.objectives == ["Write a while loop.", "Stop a loop with break."]
    kinds = [b.kind for b in page.blocks]
    assert kinds.count("exercise") == 1  # the embedded exercise has no text and is dropped
    assert kinds[-1] == "glossary"
    text = next(b for b in page.blocks if b.section == "While loops: The while statement")
    assert "The mean is x̄=(a+b)/(2) and x^2 ." in text.text
    assert "```\nwhile n > 0:\n    n -= 1\n```" in text.text
    assert "What does break do?" not in text.text  # lifted out of the prose block
    assert text.source_uri == URI + "#s2"
    exercise = next(b for b in page.blocks if b.kind == "exercise")
    assert exercise.text == "Problem: What does break do?\n\nSolution: It leaves the loop."
    assert exercise.section == "While loops: The while statement"
    assert exercise.source_uri == URI + "#e1"
    assert all(b.chapter_no == 1 and b.chapter == "Loops" for b in page.blocks)


def test_objectives_from_a_chapter_objectives_note() -> None:
    page = parse_module(
        OBJECTIVES_NOTE_MODULE, module="m3", chapter_no=2, chapter="Functions", source_uri=URI
    )
    assert page.objectives == ["Define a function."]


def _checkout(tmp_path: Path, modules: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    (root / "collections").mkdir(parents=True)
    (root / "collections" / "tiny-book.collection.xml").write_text(COLLECTION, encoding="utf-8")
    for name, xml in modules.items():
        (root / "modules" / name).mkdir(parents=True)
        (root / "modules" / name / "index.cnxml").write_text(xml, encoding="utf-8")
    return root


BOOK = CatalogBook(
    slug="tiny",
    adapter="openstax_git",
    publisher="OpenStax",
    repo="openstax/tiny",
    collection="tiny-book",
    subject_name_vi="Sách nhỏ",
    subject_name_en="Tiny book",
)


def test_built_folder_passes_the_indexers_own_validation(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path, {"m1": MODULE, "m2": MODULE, "m3": OBJECTIVES_NOTE_MODULE})
    built = build_openstax(BOOK, checkout, "abc123", tmp_path / "lib")
    assert (built.chapters, built.pages, built.licence) == (2, 3, "CC BY 4.0")
    assert built.objectives == 5
    loaded = load_book(tmp_path / "lib" / "tiny")
    assert loaded.info.license == "CC BY 4.0"
    assert loaded.info.version == "abc123"
    assert loaded.chunks
    assert (tmp_path / "lib" / "tiny" / "outline.json").exists()


def test_a_missing_module_fails_the_book_instead_of_being_skipped(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path, {"m1": MODULE, "m3": OBJECTIVES_NOTE_MODULE})
    with pytest.raises(ValueError, match=r"missing: \['m2'\]"):
        build_openstax(BOOK, checkout, "abc123", tmp_path / "lib")
