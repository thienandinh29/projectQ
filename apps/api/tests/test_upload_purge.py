import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from psycopg_pool import ConnectionPool

from app.db import create_pool
from app.jobs.queue import enqueue
from app.services.topics import TopicsService
from app.uploads.purge import purge_upload


class Storage:
    def __init__(self) -> None:
        self.objects: set[UUID] = set()
        self.removed: list[UUID] = []
        self.fail = False

    async def put(self, upload_id: UUID, body: bytes, media_type: str) -> str:
        self.objects.add(upload_id)
        return f"supabase://uploads/{upload_id}"

    async def remove(self, upload_id: UUID) -> None:
        self.removed.append(upload_id)
        if self.fail:
            raise RuntimeError("storage unavailable")
        self.objects.discard(upload_id)


@dataclass
class UploadData:
    upload: UUID
    job: UUID
    subject: UUID
    source: UUID
    chunk: UUID
    item: UUID
    external: str
    learner: UUID


@pytest.fixture
def pool(database_url: str) -> Iterator[ConnectionPool]:
    with create_pool(database_url) as value:
        yield value


def seed(pool: ConnectionPool, storage: Storage, status: str = "ready") -> UploadData:
    upload, subject, source, chunk, concept, item, learner = [uuid4() for _ in range(7)]
    external = f"upload-{item}"
    storage.objects.add(upload)
    with pool.connection() as conn:
        conn.execute(
            "insert into uploads(id,source_uri,filename,media_type,page_count,pages,text_ok) "
            "values(%s,%s,'demo.pdf','application/pdf',1,'[{\"number\":1,\"text\":\"priv"
            "ate upload\"}]',true)",
            (upload, f"supabase://uploads/{upload}"),
        )
        job = enqueue(conn, "Private demo", "free", upload_id=upload)
        slug = f"topic-{job.hex}"
        conn.execute(
            "update topic_jobs set status=%s,subject_slug=%s where id=%s", (status, slug, job)
        )
        conn.execute(
            "insert into subjects(id,slug,name_vi,name_en) values(%s,%s,'Demo','Demo')",
            (subject, slug),
        )
        conn.execute(
            "insert into sources(id,subject_id,title,license,url) "
            "values(%s,%s,'Upload','User supplied',%s)",
            (source, subject, f"supabase://uploads/{upload}"),
        )
        conn.execute(
            "insert into chunks(id,source_id,chunk_index,content,source_uri) "
            "values(%s,%s,0,'private upload',%s)",
            (chunk, source, f"supabase://uploads/{upload}"),
        )
        conn.execute(
            "insert into concepts(id,subject_id,slug,name_vi,name_en) "
            "values(%s,%s,'demo','Demo','Demo')",
            (concept, subject),
        )
        conn.execute(
            "insert into "
            "items(id,external_id,concept_id,kind,prompt,chunk_ids,status,payload) "
            "values(%s,%s,%s,'mcq','Private "
            'question\',%s,\'verified\',\'{"p4_verification":{"quote":"private '
            "upload\"}}')",
            (item, external, concept, [chunk]),
        )
        conn.execute("insert into learners(id,display_name) values(%s,'Demo')", (learner,))
        conn.execute(
            "insert into attempts(learner_id,item_id,answer,is_correct) values(%s,%s,'{}',true)",
            (learner, item),
        )
        conn.execute(
            "insert into mastery(learner_id,concept_id,p_known) values(%s,%s,0.5)",
            (learner, concept),
        )
        conn.execute(
            "insert into review_cards(learner_id,concept_id,fsrs_state,due_at) "
            "values(%s,%s,'{}',now())",
            (learner, concept),
        )
        conn.execute(
            "insert into "
            "decision_traces(learner_id,subject_id,concept_slug,kind,at,rule,rule_v"
            "i) values(%s,%s,'demo','next_item',now(),'demo','Private reason')",
            (learner, subject),
        )
        conn.execute(
            "insert into p4_learning_sessions(learner_id,subject_id,pending_item) values(%s,%s,%s)",
            (learner, subject, item),
        )
        conn.execute(
            "insert into "
            "p4_hint_cache(item_id,learner_id,cache_key,item_hash,level,attempt) "
            "values(%s,%s,%s,'hash',1,'{\"private\":true}')",
            (item, learner, external),
        )
        conn.execute(
            "insert into p4_verification_history(item_id,external_id,kind,record) "
            "values(%s,%s,'item','{\"private\":true}')",
            (item, external),
        )
        conn.execute(
            "insert into "
            "attempt_replays(learner_id,item_id,client_attempt_id,request,response)"
            " values(%s,%s,%s,'{\"private\":true}','{}')",
            (learner, external, uuid4()),
        )
        conn.execute(
            "insert into "
            "llm_calls(topic_id,tier,model,latency_ms,cost_usd,success) "
            "values(%s,'free','test',1,0,true)",
            (job,),
        )
    return UploadData(upload, job, subject, source, chunk, item, external, learner)


def assert_absent(pool: ConnectionPool, data: UploadData) -> None:
    with pool.connection() as conn:
        for table, key in (
            ("uploads", data.upload),
            ("topic_jobs", data.job),
            ("subjects", data.subject),
            ("sources", data.source),
            ("chunks", data.chunk),
            ("items", data.item),
        ):
            assert conn.execute(f"select count(*) from {table} where id=%s", (key,)).fetchone() == (
                0,
            )
        for table in (
            "attempts",
            "mastery",
            "review_cards",
            "decision_traces",
            "p4_learning_sessions",
            "attempt_replays",
            "p4_hint_cache",
        ):
            assert conn.execute(
                f"select count(*) from {table} where learner_id=%s", (data.learner,)
            ).fetchone() == (0,)
        assert conn.execute(
            "select count(*) from p4_verification_history where external_id=%s", (data.external,)
        ).fetchone() == (0,)
        assert conn.execute(
            "select count(*) from llm_calls where topic_id=%s", (data.job,)
        ).fetchone() == (0,)


def test_purge_removes_private_derived_data_and_preserves_library(pool: ConnectionPool) -> None:
    storage = Storage()
    data = seed(pool, storage)
    library, source, chunk = uuid4(), uuid4(), uuid4()
    with pool.connection() as conn:
        conn.execute(
            "insert into subjects(id,slug,name_vi,name_en) values(%s,%s,'Library','Library')",
            (library, f"library-{library}"),
        )
        conn.execute(
            "insert into sources(id,subject_id,title,license) values(%s,%s,'Public','CC BY')",
            (source, library),
        )
        conn.execute(
            "insert into chunks(id,source_id,chunk_index,content) values(%s,%s,0,'Public book')",
            (chunk, source),
        )
        # A job pointer must never make the curated subject owned by an upload.
        conn.execute(
            "update topic_jobs set subject_slug=%s where id=%s", (f"library-{library}", data.job)
        )
    service = TopicsService(lambda: pool, storage)
    assert asyncio.run(purge_upload(service, data.upload))
    assert_absent(pool, data)
    assert data.upload not in storage.objects
    assert not asyncio.run(purge_upload(service, data.upload))
    assert storage.removed == [data.upload]
    with pool.connection() as conn:
        assert conn.execute("select content from chunks where id=%s", (chunk,)).fetchone() == (
            "Public book",
        )
        conn.execute("delete from subjects where id=%s", (library,))


def test_storage_failure_rolls_back_and_can_retry(pool: ConnectionPool) -> None:
    storage = Storage()
    data = seed(pool, storage)
    storage.fail = True
    service = TopicsService(lambda: pool, storage)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        asyncio.run(purge_upload(service, data.upload))
    with pool.connection() as conn:
        assert conn.execute("select 1 from uploads where id=%s", (data.upload,)).fetchone()
        assert conn.execute("select 1 from chunks where id=%s", (data.chunk,)).fetchone()
        assert conn.execute(
            "select 1 from attempt_replays where item_id=%s", (data.external,)
        ).fetchone()
    assert data.upload in storage.objects
    storage.fail = False
    assert asyncio.run(purge_upload(service, data.upload))
    assert_absent(pool, data)


@pytest.mark.parametrize(
    "status", ["queued", "failed", "researching", "indexing", "graph", "items"]
)
def test_purge_queued_and_finished_jobs_but_refuses_active_work(
    pool: ConnectionPool, status: str
) -> None:
    storage = Storage()
    data = seed(pool, storage, status)
    service = TopicsService(lambda: pool, storage)
    if status in {"queued", "failed"}:
        assert asyncio.run(purge_upload(service, data.upload))
    else:
        with pytest.raises(HTTPException) as error:
            asyncio.run(purge_upload(service, data.upload))
        assert error.value.status_code == 409
        assert not storage.removed
        with pool.connection() as conn:
            conn.execute("update topic_jobs set status='failed' where id=%s", (data.job,))
        assert asyncio.run(purge_upload(service, data.upload))
    assert_absent(pool, data)


def test_purge_removes_retained_history_for_a_recreated_item(pool: ConnectionPool) -> None:
    storage = Storage()
    data = seed(pool, storage)
    with pool.connection() as conn:
        conn.execute(
            "insert into p4_verification_history(item_id,external_id,kind,record) "
            "values(null,%s,'invalidation','{\"old_private_quote\":true}')",
            (data.external,),
        )
    assert asyncio.run(purge_upload(TopicsService(lambda: pool, storage), data.upload))
    assert_absent(pool, data)


def test_link_metadata_can_be_purged_without_object_storage(pool: ConnectionPool) -> None:
    upload = uuid4()
    with pool.connection() as conn:
        conn.execute(
            "insert into uploads(id,source_uri,media_type,page_count,pages,text_ok) "
            "values(%s,'https://public.example/book','text/html',0,'[]',false)",
            (upload,),
        )
    service = TopicsService(lambda: pool)
    assert asyncio.run(purge_upload(service, upload))
    assert not asyncio.run(purge_upload(service, upload))
