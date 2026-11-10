"""P2 persistence adapter for P1 documents; no content generation or trust flags."""

from uuid import UUID

import psycopg

from app.config import get_settings
from app.rag.chunker import chunk_document
from app.rag.embed import Embedder, make_embedder
from app.rag.store import SourceInfo, replace_chunks, upsert_source
from app.research.pipeline import PreparedChunk
from app.schemas import ParsedDocument, SourceMeta


def index_document(
    database_url: str,
    metadata: SourceMeta,
    document: ParsedDocument,
    embedder: Embedder | None = None,
) -> list[PreparedChunk]:
    """Call from a worker thread, with canonical source metadata from the adapter.

    shortcut: changed snapshots require a new source identity; upgrade when P1/P4
    supply versioned citation migration, rather than invalidating existing items.
    """
    metadata = SourceMeta.model_validate(metadata.model_dump())
    document = ParsedDocument.model_validate(document.model_dump())
    chunks = chunk_document(document)
    if not chunks:
        raise ValueError("document has no indexable text")
    info = SourceInfo(**metadata.model_dump())
    with psycopg.connect(database_url) as conn:
        # The upsert locks the source, serializing concurrent retries before inspection.
        source_id = upsert_source(conn, info)
        rows = conn.execute(
            "select id,chapter_no,chapter,section,kind,content,source_uri,page "
            "from chunks where source_id=%s order by chunk_index",
            (source_id,),
        ).fetchall()
        expected = [
            (c.chapter_no, c.chapter, c.section, c.kind, c.content, c.source_uri, c.page)
            for c in chunks
        ]
        if rows and [tuple(row[1:]) for row in rows] != expected:
            raise ValueError("source text changed; use a new source identity to preserve citations")
        if not rows:
            if embedder is None:
                settings = get_settings()
                embedder = make_embedder(
                    settings.embedding_backend,
                    tei_url=settings.tei_url,
                    api_key=settings.tei_api_key.get_secret_value() or None,
                )
            if embedder.dim != 1024:
                raise ValueError("indexing requires bge-m3 vectors of dimension 1024")
            replace_chunks(conn, source_id, chunks, embedder)
        return _prepared(conn, source_id)


def _prepared(conn: psycopg.Connection, source_id: UUID) -> list[PreparedChunk]:
    return [
        PreparedChunk(id=str(row[0]), text=row[1], source_uri=row[2], page=row[3])
        for row in conn.execute(
            "select id,content,source_uri,page from chunks where source_id=%s order by chunk_index",
            (source_id,),
        ).fetchall()
    ]
