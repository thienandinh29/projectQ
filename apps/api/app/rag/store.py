"""Persist a source and its embedded chunks."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.rag.embed import Embedder, to_pgvector
from app.rag.notebook import Chunk


@dataclass(frozen=True)
class SourceInfo:
    subject_slug: str
    subject_name_vi: str
    subject_name_en: str
    title: str
    author: str | None
    license: str
    url: str | None
    version: str


def upsert_source(conn: psycopg.Connection, info: SourceInfo) -> UUID:
    row = conn.execute(
        "insert into subjects (slug, name_vi, name_en) values (%s, %s, %s)"
        " on conflict (slug) do update set name_vi = excluded.name_vi, name_en = excluded.name_en"
        " returning id",
        (info.subject_slug, info.subject_name_vi, info.subject_name_en),
    ).fetchone()
    assert row is not None
    row = conn.execute(
        "insert into sources (subject_id, title, author, license, url, version)"
        " values (%s, %s, %s, %s, %s, %s)"
        " on conflict (subject_id, title) do update set author = excluded.author,"
        " license = excluded.license, url = excluded.url, version = excluded.version"
        " returning id",
        (row[0], info.title, info.author, info.license, info.url, info.version),
    ).fetchone()
    assert row is not None
    source_id: UUID = row[0]
    return source_id


def replace_chunks(
    conn: psycopg.Connection,
    source_id: UUID,
    chunks: Sequence[Chunk],
    embedder: Embedder,
    *,
    batch_size: int = 64,
) -> int:
    """Swap a source's chunks for a fresh set in one transaction; returns chunks written.

    Replace rather than diff: chunk boundaries move whenever the text or chunker changes,
    and a half-replaced source would give wrong citations.
    """
    with conn.transaction():
        conn.execute("delete from chunks where source_id = %s", (source_id,))
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embedder.embed([c.embedding_text for c in batch])
            if any(len(v) != embedder.dim for v in vectors):
                raise ValueError(f"embedder returned vectors not of dim {embedder.dim}")
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into chunks (source_id, chunk_index, chapter_no, chapter, section,"
                    " kind, content, source_uri, page, embedding)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::halfvec(1024))",
                    [
                        (
                            source_id,
                            start + i,
                            c.chapter_no,
                            c.chapter,
                            c.section,
                            c.kind,
                            c.content,
                            c.source_uri,
                            c.page,
                            to_pgvector(v),
                        )
                        for i, (c, v) in enumerate(zip(batch, vectors, strict=True))
                    ],
                )
    return len(chunks)


# HNSW over halfvec, built once after bulk loading (migration 0003 drops it). m/ef_construction are
# pgvector's defaults; raising them buys recall at the cost of build time and index size.
_INDEX_SQL = (
    "create index if not exists chunks_embedding_idx"
    " on chunks using hnsw (embedding halfvec_cosine_ops)"
)


def build_vector_index(conn: psycopg.Connection) -> None:
    """Build the similarity index; idempotent. Run after loading a library, not per book."""
    conn.execute(_INDEX_SQL)


def drop_vector_index(conn: psycopg.Connection) -> None:
    """Drop the index before a large reload, then call `build_vector_index` once at the end."""
    conn.execute("drop index if exists chunks_embedding_idx")
