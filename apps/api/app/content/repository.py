"""P4 adapter over P2's pool/tables. No second database, queue or ORM.

Requires P2 to review/apply content/sql/0008_p4_runtime.sql after 0007.
All publishing reloads current relational rows and rechecks the independent audit.
"""

import struct
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.content.models import Chunk, Graph, Item, Source, digest, item_hash, validate_references
from app.content.pipeline import validate_items
from app.guardrails.answerability import is_currently_verified
from app.tutor.hints import HintAttempt

Connection = psycopg.Connection[Any]


class ContentUnavailable(RuntimeError):
    """Sanitized runtime/configuration or stale-content error."""


def stable_id(kind: str, *keys: str) -> UUID:
    return uuid5(NAMESPACE_URL, "/".join(("nodetrail-p4", kind, *keys)))


@dataclass
class StoredItem:
    db_id: UUID
    subject: str
    item: Item
    chunks: list[Chunk]
    sources: list[Source]
    revision: int

    @property
    def fingerprint(self) -> str:
        return item_hash(self.item, self.chunks)


class Repository:
    def __init__(self, pool: Callable[[], ConnectionPool]) -> None:
        self.pool = pool

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.pool().connection() as conn, conn.transaction():
            yield conn

    def require_schema(self) -> None:
        with self.transaction() as conn:
            row = conn.execute("select to_regclass('p4_hint_cache')").fetchone()
            if not row or row[0] is None:
                raise ContentUnavailable("P2 must apply the reviewed P4 runtime schema")

    def _subject(self, conn: Connection, slug: str) -> UUID:
        row = conn.execute("select id from subjects where slug=%s", (slug,)).fetchone()
        if not row:
            raise ContentUnavailable("Subject not ready")
        return UUID(str(row[0]))

    def material(self, conn: Connection, ids: list[UUID]) -> tuple[list[Source], list[Chunk]]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select c.*,s.p4_metadata as source_metadata,s.title as source_title,"
                "s.url as source_url,s.license as source_license,s.author as source_author,"
                "s.version as source_version "
                "from chunks c join sources s on s.id=c.source_id where c.id=any(%s)",
                (ids,),
            )
            rows = cur.fetchall()
        if len(rows) != len(set(ids)):
            raise ContentUnavailable("A cited chunk is missing")
        sources: dict[str, Source] = {}
        chunks = {}
        for row in rows:
            # Chapter-level inputs may share one canonical book row. Preserve
            # their original citation identity/URL in each chunk's provenance.
            meta = dict(row["p4_metadata"].get("source", row["source_metadata"]))
            if not meta:
                from app.research.runtime import indexed_library_source

                meta = indexed_library_source(
                    row["source_id"],
                    row["source_title"],
                    row["source_author"],
                    row["source_url"],
                    row["source_license"],
                    row["source_version"],
                )
            if row["p4_metadata"].get("source"):
                meta["url"] = row["source_uri"]
            else:
                meta.update(
                    title=row["source_title"],
                    url=row["source_url"],
                    license=row["source_license"],
                    author=row["source_author"] or "",
                )
            source = Source.model_validate(meta)
            sources[source.source_id] = source
            chunk = Chunk(
                chunk_id=row["id"],
                source_id=source.source_id,
                section=row["section"] or "",
                page=row["page"],
                content=row["content"],
                license=source.license,
                representation=row["p4_metadata"].get("representation", "verbatim"),
            )
            chunks[chunk.chunk_id] = chunk
        return list(sources.values()), [chunks[cid] for cid in ids]

    def save_material(self, subject: str, sources: list[Source], chunks: list[Chunk]) -> None:
        validate_references(chunks, sources)
        with self.transaction() as conn:
            conn.execute(
                "insert into subjects(id,slug,name_vi,name_en) values(%s,%s,%s,%s) "
                "on conflict do nothing",
                (stable_id("subject", subject), subject, subject, subject),
            )
            sid = self._subject(conn, subject)
            # Serialize P4 imports of a subject before source mapping/index reads.
            conn.execute("select id from subjects where id=%s for update", (sid,))
            source_ids = {}
            groups: dict[str, list[Source]] = {}
            for source in sorted(sources, key=lambda value: (value.title, value.source_id)):
                groups.setdefault(source.title, []).append(source)
            for group in groups.values():
                # One canonical update per existing book identity, avoiding alias
                # metadata flip-flops (and spurious invalidation) on identical retries.
                source = group[-1]
                source_key = stable_id("source", subject, group[0].source_id)
                existing = conn.execute(
                    "select title from sources where id=%s and subject_id=%s", (source_key, sid)
                ).fetchone()
                # Search titles can change for the same URL; retain its durable book identity.
                canonical_title = existing[0] if existing else source.title
                conn.execute(
                    "insert into sources(id,subject_id,title,author,license,url,versio"
                    "n,p4_metadata) "
                    "values(%s,%s,%s,%s,%s,%s,%s,%s) on conflict(subject_id,title) do update set "
                    "author=excluded.author,license=excluded.license,url=excluded.url,"
                    "version=excluded.version,p4_metadata=excluded.p4_metadata "
                    "where (sources.author,sources.license,sources.url,sources.version"
                    ",sources.p4_metadata) "
                    "is distinct from (excluded.author,excluded.license,excluded.url,e"
                    "xcluded.version,"
                    "excluded.p4_metadata)",
                    (
                        source_key,
                        sid,
                        canonical_title,
                        source.author,
                        source.license,
                        source.url,
                        source.version,
                        Jsonb(source.model_dump(mode="json")),
                    ),
                )
                row = conn.execute(
                    "select id from sources where subject_id=%s and title=%s",
                    (sid, canonical_title),
                ).fetchone()
                assert row
                for alias in group:
                    source_ids[alias.source_id] = row[0]
            # Source upserts lock the same book rows used by P2's index_document.
            # Allocate against actual DB IDs, not input chapter source IDs.
            indices: dict[UUID, int] = {}
            for source_id in sorted(set(source_ids.values())):
                conn.execute("select id from sources where id=%s for update", (source_id,))
                maximum = conn.execute(
                    "select coalesce(max(chunk_index),-1) from chunks where source_id=%s",
                    (source_id,),
                ).fetchone()
                assert maximum is not None
                indices[source_id] = maximum[0] + 1
            for chunk in chunks:
                database_source = source_ids[chunk.source_id]
                # UUIDs come from P1/the caller; never allocate new chunk IDs on retry.
                current = conn.execute(
                    "select source_id,chunk_index from chunks where id=%s", (chunk.chunk_id,)
                ).fetchone()
                if current and current[0] != source_ids[chunk.source_id]:
                    raise ContentUnavailable("Chunk ID belongs to another source")
                if current:
                    index = current[1]
                else:
                    index = indices[database_source]
                    indices[database_source] += 1
                source = next(s for s in sources if s.source_id == chunk.source_id)
                conn.execute(
                    "insert into chunks(id,source_id,chunk_index,chapter,section,page,content,"
                    "source_uri,p4_metadata) values(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "on conflict(id) do update set content=excluded.content,section=ex"
                    "cluded.section,"
                    "embedding=case when chunks.content is distinct from excluded.content "
                    "then null else chunks.embedding end,"
                    "page=excluded.page,source_uri=excluded.source_uri,p4_metadata=exc"
                    "luded.p4_metadata "
                    "where (chunks.content,chunks.section,chunks.page,chunks.source_ur"
                    "i,chunks.p4_metadata) "
                    "is distinct from (excluded.content,excluded.section,excluded.page"
                    ",excluded.source_uri,"
                    "excluded.p4_metadata)",
                    (
                        chunk.chunk_id,
                        source_ids[chunk.source_id],
                        index,
                        chunk.section,
                        chunk.section,
                        chunk.page,
                        chunk.content,
                        source.url,
                        Jsonb(
                            {
                                "representation": chunk.representation,
                                "source": source.model_dump(mode="json"),
                            }
                        ),
                    ),
                )

    def graph(self, conn: Connection, subject: str) -> Graph:
        row = conn.execute("select p4_graph from subjects where slug=%s", (subject,)).fetchone()
        if not row or not row[0]:
            raise ContentUnavailable("Graph not ready")
        return Graph.model_validate(row[0])

    def save_graph(self, subject: str, graph: Graph) -> None:
        value = graph.model_dump(mode="json", by_alias=True)
        with self.transaction() as conn:
            sid = self._subject(conn, subject)
            old = conn.execute(
                "select p4_graph from subjects where id=%s for update", (sid,)
            ).fetchone()
            if old and old[0] == value:
                return
            ids = list(dict.fromkeys(cid for c in graph.concepts for cid in c.chunk_ids))
            sources, chunks = self.material(conn, ids)
            validate_references(chunks, sources, graph)
            for concept in graph.concepts:
                cid = stable_id("concept", subject, concept.slug)
                conn.execute(
                    "insert into concepts(id,subject_id,slug,name_vi,name_en,description) "
                    "values(%s,%s,%s,%s,%s,%s) on conflict(subject_id,slug) do update set "
                    "name_vi=excluded.name_vi,name_en=excluded.name_en,descriptio"
                    "n=excluded.description",
                    (
                        cid,
                        sid,
                        concept.slug,
                        concept.name_vi,
                        concept.name_en,
                        concept.description_vi,
                    ),
                )
                actual = conn.execute(
                    "select id from concepts where subject_id=%s and slug=%s", (sid, concept.slug)
                ).fetchone()
                assert actual
                conn.execute("delete from concept_sources where concept_id=%s", (actual[0],))
                for chunk_id in concept.chunk_ids:
                    conn.execute(
                        "insert into concept_sources(concept_id,chunk_id) values(%s,%s)",
                        (actual[0], chunk_id),
                    )
            conn.execute(
                "delete from concept_edges where concept_id in "
                "(select id from concepts where subject_id=%s)",
                (sid,),
            )
            for edge in graph.edges:
                conn.execute(
                    "insert into concept_edges(prerequisite_id,concept_id) select a.id,b.id "
                    "from concepts a,concepts b where a.subject_id=%s and b.subject_id=%s "
                    "and a.slug=%s and b.slug=%s",
                    (sid, sid, edge.prerequisite, edge.to),
                )
            conn.execute("update subjects set p4_graph=%s where id=%s", (Jsonb(value), sid))

    def load_item(self, conn: Connection, external_id: str) -> StoredItem | None:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select i.*,i.difficulty::double precision as difficulty,"
                "c.slug as concept_slug,s.slug as subject_slug from items i "
                "join concepts c on c.id=i.concept_id join subjects s on s.id=c.subject_id "
                "where i.external_id=%s for update of i",
                (external_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        data = dict(row["payload"].get("p4_item", {}))
        if not data:
            return None
        sources, chunks = self.material(conn, row["chunk_ids"])
        original = Item.model_validate(data)
        known_ids = {stable_id("option", str(row["id"]), o.id): o.id for o in original.options}
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select o.*,m.slug as misconception_slug from item_options o "
                "left join misconceptions m on m.id=o.misconception_id "
                "where o.item_id=%s order by o.position",
                (row["id"],),
            )
            options = [
                {
                    "id": known_ids.get(o["id"], str(o["id"])),
                    "label": o["label"],
                    "correct": o["is_correct"],
                    "misconception": o["misconception_slug"],
                }
                for o in cur.fetchall()
            ]
        data.update(
            id=row["external_id"],
            concept=row["concept_slug"],
            prompt_vi=row["prompt"],
            kind=row["kind"],
            chunk_ids=[str(cid) for cid in row["chunk_ids"]],
            status=row["status"],
            options=options,
            verification=row["payload"].get("p4_verification"),
        )
        # Postgres REAL is float32; preserve the authored value only when its
        # stored float32 representation still matches the actual relational row.
        if struct.pack("f", original.difficulty) != struct.pack("f", row["difficulty"]):
            data["difficulty"] = row["difficulty"]
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select slug,description_vi from misconceptions where concept_id=%s",
                (row["concept_id"],),
            )
            descriptions = {m["slug"]: m["description_vi"] for m in cur.fetchall()}
        data["misconceptions"] = [
            {"slug": m.slug, "description_vi": descriptions[m.slug]}
            for m in original.misconceptions
            if m.slug in descriptions
        ]
        if data["source"] not in {s.url for s in sources} and len(sources) == 1:
            data["source"] = sources[0].url
        try:
            item = Item.model_validate(data)
            return StoredItem(
                row["id"], row["subject_slug"], item, chunks, sources, row["p4_revision"]
            )
        except ValueError:
            return None

    def misconception_descriptions(
        self, conn: Connection, subject: str
    ) -> dict[tuple[str, str], str]:
        return {
            (concept, slug): description
            for concept, slug, description in conn.execute(
                "select c.slug,m.slug,m.description_vi from misconceptions m "
                "join concepts c on c.id=m.concept_id join subjects s on s.id=c.subject_id "
                "where s.slug=%s",
                (subject,),
            )
        }

    def current(self, conn: Connection, external_id: str) -> StoredItem | None:
        try:
            bundle = self.load_item(conn, external_id)
            if (
                bundle
                and all(s.model_ingestion_allowed for s in bundle.sources)
                and is_currently_verified(bundle.item, bundle.chunks)
            ):
                return bundle
        except (ValueError, ContentUnavailable):
            pass
        return None

    def servable(self, conn: Connection, external_id: str) -> StoredItem | None:
        """Learner gate additionally excludes partially committed/failed topic jobs."""
        bundle = self.current(conn, external_id)
        if bundle and bundle.subject.startswith("topic-"):
            ready = conn.execute(
                "select 1 from topic_jobs where subject_slug=%s "
                "and status='ready' and items_ready=true",
                (bundle.subject,),
            ).fetchone()
            if not ready:
                return None
        return bundle

    def save_items(self, subject: str, items: list[Item]) -> None:
        with self.transaction() as conn:
            graph = self.graph(conn, subject)
            ids = list(
                dict.fromkeys(
                    [cid for c in graph.concepts for cid in c.chunk_ids]
                    + [cid for item in items for cid in item.chunk_ids]
                )
            )
            sources, chunks = self.material(conn, ids)
            validate_items(items, chunks, sources, graph)
            sid = self._subject(conn, subject)
            for item in items:
                cid = conn.execute(
                    "select id from concepts where subject_id=%s and slug=%s", (sid, item.concept)
                ).fetchone()
                assert cid
                for misconception in item.misconceptions:
                    conn.execute(
                        "insert into misconceptions(id,concept_id,slug,description_vi) val"
                        "ues(%s,%s,%s,%s) "
                        "on conflict(concept_id,slug) do nothing",
                        (
                            stable_id("misconception", str(cid[0]), misconception.slug),
                            cid[0],
                            misconception.slug,
                            misconception.description_vi,
                        ),
                    )
                content = item.model_dump(mode="json", exclude={"verification", "status"})
                payload = {"p4_item": content}
                existing = conn.execute(
                    "select id,payload,chunk_ids from items where external_id=%s for update",
                    (item.id,),
                ).fetchone()
                if existing:
                    dbid = existing[0]
                    owner = conn.execute(
                        "select c.subject_id from items i join concepts c on c.id=i.concept_id "
                        "where i.id=%s",
                        (dbid,),
                    ).fetchone()
                    if not owner or owner[0] != sid:
                        raise ContentUnavailable("External item ID belongs to another subject")
                    # Identical retries preserve mastery and their existing audit.
                    unchanged = (
                        existing[1].get("p4_item") == content and existing[2] == item.chunk_ids
                    )
                    if not unchanged:
                        conn.execute(
                            "update items set concept_id=%s,prompt=%s,payload=%s,difficulty=%s,"
                            "chunk_ids=%s,status='needs_review' where id=%s",
                            (
                                cid[0],
                                item.prompt_vi,
                                Jsonb(payload),
                                item.difficulty,
                                item.chunk_ids,
                                dbid,
                            ),
                        )
                        conn.execute("delete from item_options where item_id=%s", (dbid,))
                else:
                    unchanged = False
                    dbid = stable_id("item", subject, item.id)
                    conn.execute(
                        "insert into items(id,external_id,concept_id,kind,prompt,payload,d"
                        "ifficulty,"
                        "chunk_ids) values(%s,%s,%s,'mcq',%s,%s,%s,%s)",
                        (
                            dbid,
                            item.id,
                            cid[0],
                            item.prompt_vi,
                            Jsonb(payload),
                            item.difficulty,
                            item.chunk_ids,
                        ),
                    )
                if not unchanged:
                    for position, option in enumerate(item.options):
                        mid = None
                        if option.misconception:
                            found = conn.execute(
                                "select id from misconceptions where concept_id=%s and slug=%s",
                                (cid[0], option.misconception),
                            ).fetchone()
                            assert found
                            mid = found[0]
                        conn.execute(
                            "insert into item_options(id,item_id,label,is_correct,misconceptio"
                            "n_id,position) "
                            "values(%s,%s,%s,%s,%s,%s)",
                            (
                                stable_id("option", str(dbid), option.id),
                                dbid,
                                option.label,
                                option.correct,
                                mid,
                                position,
                            ),
                        )
                # Check the audit against current DB rows, not just the pre-call snapshot.
                conn.execute(
                    "update items set payload=jsonb_set(payload,'{p4_verification}',%s"
                    ") where id=%s",
                    (
                        Jsonb(
                            item.verification.model_dump(mode="json") if item.verification else None
                        ),
                        dbid,
                    ),
                )
                loaded = self.load_item(conn, item.id)
                valid = bool(
                    loaded
                    and all(source.model_ingestion_allowed for source in sources)
                    and item.verification
                    and item.verification.content_hash == loaded.fingerprint
                    and is_currently_verified(item, loaded.chunks)
                )
                conn.execute(
                    "update items set status=%s where id=%s",
                    ("verified" if valid else "needs_review", dbid),
                )

    def item_ids(self, conn: Connection, subject: str) -> list[str]:
        return [
            r[0]
            for r in conn.execute(
                "select i.external_id from items i join concepts c on c.id=i.concept_id "
                "join subjects s on s.id=c.subject_id where s.slug=%s "
                "and i.external_id is not null order by i.external_id",
                (subject,),
            )
        ]

    def hint_history(
        self, conn: Connection, bundle: StoredItem, learner: UUID, level: int
    ) -> list[str]:
        return [
            row[0]["draft"]["hint_vi"]
            for row in conn.execute(
                "select attempt from p4_hint_cache where item_id=%s and learner_id"
                "=%s and level<%s "
                "and item_hash=%s and invalidated_at is null order by level,created_at",
                (bundle.db_id, learner, level, bundle.fingerprint),
            )
        ]

    def save_hint(
        self,
        conn: Connection,
        bundle: StoredItem,
        learner: UUID,
        key: str,
        level: int,
        attempt: HintAttempt,
    ) -> bool:
        current = self.current(conn, bundle.item.id)
        if (
            not current
            or current.revision != bundle.revision
            or current.fingerprint != bundle.fingerprint
        ):
            return False
        data = attempt.model_dump(mode="json")
        conn.execute(
            "insert into p4_verification_history(item_id,external_id,kind,reco"
            "rd) values(%s,%s,'hint',%s)",
            (bundle.db_id, bundle.item.id, Jsonb(data)),
        )
        if attempt.verification.status == "verified":
            conn.execute(
                "insert into p4_hint_cache(item_id,learner_id,cache_key,item_hash,level,attempt) "
                "values(%s,%s,%s,%s,%s,%s) on conflict(cache_key) do update set "
                "attempt=excluded.attempt,created_at=now(),invalidated_at=null "
                "where p4_hint_cache.invalidated_at is not null",
                (bundle.db_id, learner, key, bundle.fingerprint, level, Jsonb(data)),
            )
        return True

    @staticmethod
    def cache_key(
        bundle: StoredItem,
        learner: UUID,
        level: int,
        tier: str,
        last_answer: str | None,
        history: list[str],
    ) -> str:
        from app.tutor.hints import PROMPT_VERSION

        return digest(
            [bundle.fingerprint, str(learner), level, tier, last_answer, history, PROMPT_VERSION]
        )
