import asyncio
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from fastapi import HTTPException

from app.api.topics import TopicInput
from app.db import create_pool
from app.jobs.queue import append_trail, enqueue, snapshot
from app.jobs.worker import run_once
from app.services.topics import SupabaseStorage, TopicsService, load_upload
from app.uploads.reader import Document, Page
from tests.research.test_pipeline import Ports, pipeline


def test_worker_calls_pipeline_and_persists_partial_failure(database_url: str) -> None:
    ports = Ports()
    ports.items[0] = ports.items[0].model_copy(update={"status": "needs_review"})
    with psycopg.connect(database_url) as conn:
        topic_id = enqueue(conn, "Pipeline contract", "free")
    assert run_once(database_url, pipeline=pipeline(ports))
    with psycopg.connect(database_url) as conn:
        state = snapshot(conn, topic_id)
        assert state is not None
        assert state["status"] == "failed"
        assert not state["graph_ready"] and not state["items_ready"]
        assert ports.graph_saved  # private checkpoint, not a published learner graph
        assert state["subject_slug"] == "biology"
        assert state["sources"][0]["publisher"] == "Publisher"
        assert "text" not in state["sources"][0]
        conn.execute("delete from topic_jobs where id=%s", (topic_id,))


def test_worker_calls_pipeline_and_publishes_ready(database_url: str) -> None:
    ports = Ports()
    with psycopg.connect(database_url) as conn:
        topic_id = enqueue(conn, "Worker success", "free")
        append_trail(conn, topic_id, {"kind": "select", "text_vi": "Nguồn đã chọn"})
    assert run_once(database_url, pipeline=pipeline(ports))
    with psycopg.connect(database_url) as conn:
        state = snapshot(conn, topic_id)
        assert state is not None
        assert state["status"] == "ready" and state["progress"] == 1
        assert state["graph_ready"] and state["items_ready"]
        assert state["trail"][0]["kind"] == "select"
        assert ports.graph_saved and ports.items_saved
        conn.execute("delete from topic_jobs where id=%s", (topic_id,))


def test_upload_roundtrip_and_complete_job_input(database_url: str) -> None:
    with create_pool(database_url) as pool:
        service = TopicsService(lambda: pool)
        document = Document(
            "https://books.example/a", (Page(1, "Nội dung học"),), True, "text/html"
        )
        upload_id = asyncio.run(service.persist_upload(document, None, None))
        assert load_upload(database_url, upload_id) == document
        request = TopicInput(upload_id=upload_id, tier="pro", mode="deep")
        result = asyncio.run(service.enqueue(request))
        with pool.connection() as conn:
            row = conn.execute(
                "select goal_vi,mode,tier,upload_id from topic_jobs where id=%s",
                (UUID(result.topic_id),),
            ).fetchone()
            assert row == ("", "deep", "pro", UUID(upload_id))
            conn.execute("delete from topic_jobs where id=%s", (UUID(result.topic_id),))
            conn.execute("delete from uploads where id=%s", (UUID(upload_id),))
        with pytest.raises(HTTPException) as error:
            asyncio.run(
                service.enqueue(TopicInput(upload_id=str(uuid4()), tier="free", mode="quick"))
            )
        assert error.value.status_code == 404


def test_storage_cleanup_on_metadata_failure(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Storage:
        written: UUID | None = None
        removed: UUID | None = None

        async def put(self, upload_id: UUID, body: bytes, media_type: str) -> str:
            self.written = upload_id
            return f"supabase://uploads/{upload_id}"

        async def remove(self, upload_id: UUID) -> None:
            self.removed = upload_id

    storage = Storage()
    with create_pool(database_url) as pool:
        service = TopicsService(lambda: pool, storage)

        def fail(metadata: object) -> None:
            raise RuntimeError("insertion failed")

        monkeypatch.setattr(service, "_save_upload", fail)
        with pytest.raises(RuntimeError, match="insertion failed"):
            asyncio.run(
                service.persist_upload(
                    Document("", (Page(1, "Text"),), True, "application/pdf"), b"PDF", "a.pdf"
                )
            )
        assert storage.written is not None and storage.written == storage.removed


@pytest.mark.parametrize("public", [True, False])
def test_storage_rejects_public_bucket(public: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer test-secret"
        assert "test-secret" not in str(request.url)
        if request.method == "GET":
            return httpx.Response(200, json={"public": public})
        return httpx.Response(200, json={})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.topics.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    storage = SupabaseStorage("https://storage.example", "test-secret")
    upload_id = uuid4()
    if public:
        with pytest.raises(HTTPException) as error:
            asyncio.run(storage.put(upload_id, b"pdf", "application/pdf"))
        assert error.value.status_code == 503
        assert len(requests) == 1
    else:
        uri = asyncio.run(storage.put(upload_id, b"pdf", "application/pdf"))
        assert uri == f"supabase://uploads/{upload_id}"
        assert requests[-1].headers["x-upsert"] == "false"
        asyncio.run(storage.remove(upload_id))
        assert requests[-1].method == "DELETE"
        assert str(upload_id).encode() in requests[-1].content
