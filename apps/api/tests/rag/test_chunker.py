"""The generic chunker: size, location and no-loss guarantees, on tidy and ugly input."""

import random
import unicodedata

import pytest

from app.rag.chunker import chunk_document, pack, split_text
from app.schemas import DocBlock, ParsedDocument


def block(text: str, **kw: object) -> DocBlock:
    fields: dict[str, object] = {
        "chapter_no": 1,
        "chapter": "Chương 1",
        "section": "Mở đầu",
        "text": text,
        "source_uri": "https://x/book#s1",
    }
    return DocBlock.model_validate({**fields, **kw})


def doc(*blocks: DocBlock) -> ParsedDocument:
    return ParsedDocument(blocks=list(blocks))


def squash(text: str) -> str:
    """Text without whitespace: what must never be lost or reordered."""
    return "".join(unicodedata.normalize("NFC", text).split())


# --- split_text --------------------------------------------------------------------------------


def test_short_text_is_returned_whole_and_blank_is_nothing() -> None:
    assert split_text("  một câu ngắn.  ", 100) == ["một câu ngắn."]
    assert split_text("   \n\n ", 100) == []


def test_limit_must_be_positive() -> None:
    with pytest.raises(ValueError):
        split_text("x", 0)


def test_paragraphs_stay_whole_when_they_fit() -> None:
    text = "AAAA aaaa.\n\nBBBB bbbb.\n\nCCCC cccc."
    assert split_text(text, 12) == ["AAAA aaaa.", "BBBB bbbb.", "CCCC cccc."]
    assert split_text(text, 24) == ["AAAA aaaa.\n\nBBBB bbbb.", "CCCC cccc."]


def test_a_huge_paragraph_without_newlines_splits_at_sentences() -> None:
    sentences = [f"Đây là câu số {i} của đoạn rất dài." for i in range(40)]
    pieces = split_text(" ".join(sentences), 200)
    assert len(pieces) > 1 and all(len(p) <= 200 for p in pieces)
    assert all(p.endswith(".") for p in pieces)  # cut on sentence ends, not mid-sentence


def test_text_without_sentence_ends_splits_at_words() -> None:
    pieces = split_text("từ " * 300, 100)
    assert all(len(p) <= 100 and not p.startswith(" ") for p in pieces)
    assert squash("".join(pieces)) == squash("từ " * 300)


def test_an_unbroken_run_is_hard_cut() -> None:
    url = "https://example.org/" + "a" * 500
    pieces = split_text(url, 120)
    assert len(pieces) == 5 and all(len(p) <= 120 for p in pieces)
    assert "".join(pieces) == url


def test_code_indentation_survives_a_split() -> None:
    code = "\n".join(["def f(x):", "    if x:", "        return 1", "    return 0"] * 20)
    pieces = split_text(code, 150)
    assert len(pieces) > 1
    lines = [ln for p in pieces for ln in p.splitlines()]
    assert lines == code.splitlines()  # every line intact, indentation included


# --- pack and chunk_document -------------------------------------------------------------------


def test_pack_joins_with_a_blank_line_up_to_the_limit() -> None:
    assert pack(["aaaa", "bbbb", "cccc"], 10) == ["aaaa\n\nbbbb", "cccc"]
    assert pack(["", "  "], 10) == []


def test_adjacent_blocks_in_the_same_place_are_packed_together() -> None:
    chunks = chunk_document(doc(block("Câu một."), block("Câu hai."), block("")))
    assert [c.content for c in chunks] == ["Câu một.\n\nCâu hai."]
    assert chunks[0].chapter == "Chương 1" and chunks[0].source_uri == "https://x/book#s1"


@pytest.mark.parametrize(
    "change",
    [
        {"section": "Mục khác"},
        {"chapter": "Chương 2", "chapter_no": 2},
        {"kind": "exercise"},
        {"source_uri": "https://x/book#s2"},
        {"page": 2},
    ],
)
def test_blocks_are_never_merged_across_a_change_of_location(change: dict[str, object]) -> None:
    chunks = chunk_document(doc(block("Một."), block("Hai.", **change)))
    assert len(chunks) == 2


def test_the_page_is_kept_so_a_citation_opens_the_right_pdf_page() -> None:
    chunks = chunk_document(doc(block("Trang ba.", page=3), block("Trang bốn.", page=4)))
    assert [(c.page, c.content) for c in chunks] == [(3, "Trang ba."), (4, "Trang bốn.")]


def test_an_upload_without_chapters_works() -> None:
    chunks = chunk_document(doc(block("Nội dung.", chapter_no=None, page=1)))
    assert chunks[0].chapter_no is None and chunks[0].page == 1


def test_vietnamese_is_normalised_to_nfc() -> None:
    decomposed = unicodedata.normalize("NFD", "Biểu thức boolean")
    chunk = chunk_document(doc(block(decomposed, section=decomposed)))[0]
    assert chunk.content == "Biểu thức boolean" and chunk.section == "Biểu thức boolean"


def test_a_block_longer_than_the_limit_is_split_into_chunks_at_the_same_place() -> None:
    chunks = chunk_document(doc(block("Câu. " * 100, page=7)), max_chars=120)
    assert len(chunks) > 3 and all(len(c.content) <= 120 for c in chunks)
    assert {(c.page, c.section) for c in chunks} == {(7, "Mở đầu")}


def test_output_is_deterministic() -> None:
    d = doc(*(block(f"Đoạn {i}. " * 30, section=f"Mục {i % 3}") for i in range(12)))
    assert chunk_document(d, max_chars=300) == chunk_document(d, max_chars=300)


# --- randomised: the two guarantees that matter ------------------------------------------------

_WORDS = ["biểu", "thức", "x", "if", "==", "boolean", "Vòng", "lặp", "a" * 40, "3.14", "e.g."]


def _random_text(rng: random.Random) -> str:
    parts: list[str] = []
    for _ in range(rng.randint(0, 12)):
        words = " ".join(rng.choice(_WORDS) for _ in range(rng.randint(1, 60)))
        words += rng.choice([".", "!", "?", "", " ...", "\n    indented()", "\n"])
        parts.append(words)
    return rng.choice(["\n\n", "\n", " ", "\n \n"]).join(parts)


@pytest.mark.parametrize("seed", range(40))
def test_no_oversized_chunk_and_no_lost_text_on_random_documents(seed: int) -> None:
    rng = random.Random(seed)
    limit = rng.choice([40, 80, 200, 1800])
    blocks = [
        block(
            _random_text(rng),
            section=rng.choice(["A", "B"]),
            page=rng.choice([None, 1, 2]),
            kind=rng.choice(["text", "text", "exercise"]),
        )
        for _ in range(rng.randint(1, 8))
    ]
    chunks = chunk_document(doc(*blocks), max_chars=limit)
    assert all(len(c.content) <= limit for c in chunks)
    # Nothing lost or reordered: the words of all chunks in order are the words of the blocks.
    assert squash("".join(c.content for c in chunks)) == squash("".join(b.text for b in blocks))
