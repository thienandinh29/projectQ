"""Cited retrieval: question in, best-matching textbook chunks out (contract: TEAM.md).

`search(query, subject, k=5) -> list[Citation]`. Every explanation, hint and generated item must
trace back to the chunks returned here, so each `Citation` carries what the web app needs to show
the source and open the original page (`source_uri`, plus `page` for uploaded PDFs).

The query vector comes from an `AsyncEmbedder` (TEI in production), so the event loop is never
blocked; the SQL runs on the sync connection pool in a worker thread.
"""

import asyncio
import unicodedata
from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool

from app.rag.embed import EMBEDDING_DIM, AsyncEmbedder, to_pgvector
from app.schemas import Citation

MAX_K = 50

# `<=>` is cosine *distance*; similarity is 1 - distance. The inner ORDER BY keeps the bare
# distance expression so the HNSW index (halfvec_cosine_ops) can serve it. Iterative scans may
# return rows slightly out of order (see `_allow_filtered_scan`), so the outer query re-sorts the
# k rows exactly.
_SQL = f"""
with nearest as materialized (
    select c.id, s.title, c.chapter, c.section, s.license, c.source_uri, c.page, c.content,
           c.embedding <=> %(q)s::halfvec({EMBEDDING_DIM}) as distance
    from chunks c
    join sources s on s.id = c.source_id
    join subjects sub on sub.id = s.subject_id
    where sub.slug = %(subject)s
      and (%(chunk_ids)s::uuid[] is null or c.id = any(%(chunk_ids)s::uuid[]))
      and c.embedding is not null
    order by distance
    limit %(k)s
)
select id, title, chapter, section, license, source_uri, page, content, 1 - distance as score
from nearest
order by distance + 0
"""


@dataclass(frozen=True)
class Retriever:
    """Holds what `search` needs, so callers keep the contract's `(query, subject, k)` shape."""

    pool: ConnectionPool
    embedder: AsyncEmbedder
    chunk_ids: tuple[UUID, ...] | None = None

    async def search(self, query: str, subject: str, k: int = 5) -> list[Citation]:
        text = unicodedata.normalize("NFC", query).strip()  # Vietnamese: composed form, as indexed
        if not text:
            raise ValueError("query must not be empty")
        if not 1 <= k <= MAX_K:
            raise ValueError(f"k must be between 1 and {MAX_K}")
        (vector,) = await self.embedder.aembed([text])
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(f"query embedding is not {EMBEDDING_DIM}-dimensional")
        return await asyncio.to_thread(self._query, to_pgvector(vector), subject, k)

    def _query(self, vector: str, subject: str, k: int) -> list[Citation]:
        with self.pool.connection() as conn, conn.transaction():
            _allow_filtered_scan(conn)
            rows = conn.execute(
                _SQL,
                {
                    "q": vector,
                    "subject": subject,
                    "k": k,
                    "chunk_ids": list(self.chunk_ids) if self.chunk_ids is not None else None,
                },
            ).fetchall()
        return [
            Citation(
                chunk_id=str(row[0]),
                source_title=row[1],
                chapter=row[2],
                section=row[3],
                license=row[4],
                source_uri=row[5],
                page=row[6],
                content=row[7],
                score=float(row[8]),
            )
            for row in rows
        ]


async def search(query: str, subject: str, k: int = 5, *, retriever: Retriever) -> list[Citation]:
    """The contract's `search(query, subject, k)`; the retriever is created once at startup."""
    return await retriever.search(query, subject, k)


def _allow_filtered_scan(conn: psycopg.Connection) -> None:
    """Keep scanning the HNSW index until `k` rows pass the subject filter (pgvector >= 0.8).

    Without it, a selective filter can return fewer than `k` rows (the index yields only
    `hnsw.ef_search` candidates before the filter). Older pgvector lacks the setting; the plain
    query still works, just with that limitation, so a missing setting is not an error.
    """
    try:
        with conn.transaction():  # savepoint: a failed SET must not abort the query's transaction
            conn.execute("set local hnsw.iterative_scan = relaxed_order")
    except psycopg.errors.UndefinedObject:
        pass
    except psycopg.errors.InvalidParameterValue:
        pass
