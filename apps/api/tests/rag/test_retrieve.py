"""Retriever against a real migrated pgvector database, with the deterministic fake embedder."""

import asyncio
import unicodedata
from dataclasses import replace
from uuid import UUID

import psycopg
import pytest

from app.rag.notebook import parse_notebook
from app.rag.retrieve import Retriever, search
from tests.rag.fixtures import NOTEBOOK


def _glossary_text() -> str:
    chunk = next(c for c in parse_notebook(NOTEBOOK, 5) if c.kind == "glossary")
    return chunk.embedding_text


def test_exact_text_is_the_top_hit_with_full_citation_fields(retriever: Retriever) -> None:
    hits = asyncio.run(retriever.search(_glossary_text(), "python", k=3))
    top = hits[0]
    assert top.score == pytest.approx(1.0, abs=1e-3)
    assert "modulus operator" in top.content
    assert top.source_title == "Think Python"
    assert top.license == "CC BY-NC-SA 4.0"
    assert top.chapter == "Conditionals and Recursion"
    assert top.section == "Glossary"
    assert top.source_uri.startswith("https://allendowney.github.io/ThinkPython/chap05.html")
    assert top.page is None and top.publisher is None
    assert top.chunk_id


def test_results_are_ranked_and_limited_to_k(retriever: Retriever) -> None:
    hits = asyncio.run(retriever.search(_glossary_text(), "python", k=4))
    assert len(hits) == 4
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_search_is_scoped_to_the_subject(retriever: Retriever) -> None:
    bio = asyncio.run(retriever.search(_glossary_text(), "biology", k=10))
    assert [h.source_title for h in bio] == ["Biology 2e"]  # one chunk only; no Python leakage
    py = asyncio.run(retriever.search("cell membrane", "python", k=50))
    assert py and all(h.source_title == "Think Python" for h in py)


def test_unknown_subject_returns_nothing_instead_of_failing(retriever: Retriever) -> None:
    assert asyncio.run(retriever.search("anything", "no-such-subject")) == []


def test_retry_context_excludes_older_material_from_same_topic(retriever: Retriever) -> None:
    hits = asyncio.run(retriever.search(_glossary_text(), "python", k=4))
    allowed = UUID(hits[-1].chunk_id)
    scoped = replace(retriever, chunk_ids=(allowed,))
    assert [h.chunk_id for h in asyncio.run(scoped.search(_glossary_text(), "python", k=4))] == [
        str(allowed)
    ]
    assert asyncio.run(replace(retriever, chunk_ids=()).search("anything", "python")) == []


def test_query_is_nfc_normalised_so_decomposed_vietnamese_matches(retriever: Retriever) -> None:
    composed = "Biểu thức boolean là gì?"
    decomposed = unicodedata.normalize("NFD", composed)
    a = asyncio.run(retriever.search(composed, "python", k=2))
    b = asyncio.run(retriever.search(decomposed, "python", k=2))
    assert [h.chunk_id for h in a] == [h.chunk_id for h in b]
    assert [h.score for h in a] == pytest.approx([h.score for h in b])


@pytest.mark.parametrize(("query", "k"), [("", 5), ("   ", 5), ("ok", 0), ("ok", 51)])
def test_bad_arguments_are_rejected(retriever: Retriever, query: str, k: int) -> None:
    with pytest.raises(ValueError):
        asyncio.run(retriever.search(query, "python", k))


def test_module_level_search_matches_the_contract_shape(retriever: Retriever) -> None:
    hits = asyncio.run(search(_glossary_text(), "python", retriever=retriever))
    assert len(hits) == 5  # default k


def test_works_with_the_hnsw_index_built(database_url: str, retriever: Retriever) -> None:
    from app.rag.store import build_vector_index, drop_vector_index

    with psycopg.connect(database_url) as conn:
        build_vector_index(conn)
    try:
        hits = asyncio.run(retriever.search(_glossary_text(), "python", k=3))
        assert hits[0].score == pytest.approx(1.0, abs=1e-3)
        assert len(hits) == 3
    finally:
        with psycopg.connect(database_url) as conn:
            drop_vector_index(conn)
