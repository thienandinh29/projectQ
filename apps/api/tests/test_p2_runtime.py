"""P2/P4 factory wiring with fake storage/database; no live acceptance claim."""

from contextlib import nullcontext
from io import BytesIO
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pypdf import PdfWriter

from app.config import Settings
from app.content.learning import graph_revision
from app.content.repository import ContentUnavailable, Repository
from app.db import create_pool
from app.main import create_content_app
from app.services.topics import TopicsService
from app.uploads.metadata import UploadMetadata
from app.uploads.reader import Document, Page
from tests.content.fakes import FakeGateway, topic
from tests.uploads.test_reader import docx


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> tuple[Settings, Mock, Mock, Mock]:
    pool = Mock()
    monkeypatch.setattr("app.main.create_pool", lambda url: pool)
    monkeypatch.setattr(
        "app.services.learner_sessions.LearnerSessions.require_schema", lambda self: None
    )
    monkeypatch.setattr(
        "app.services.graph_confirmation.GraphConfirmations.require_schema", lambda self: None
    )
    monkeypatch.setattr(
        "app.services.graph_confirmation.GraphConfirmations.__call__", lambda *args: False
    )
    store = Mock(spec=Repository)
    storage = Mock()

    async def put(upload_id: UUID, body: bytes, media_type: str) -> str:
        return f"supabase://uploads/{upload_id}"

    async def remove(upload_id: UUID) -> None:
        storage.removed = upload_id

    storage.put = put
    storage.remove = remove
    monkeypatch.setattr("app.main.SupabaseStorage", lambda *args: storage)
    settings = Settings(
        _env_file=None,
        api_key="local-test-key",
        demo_uploads_enabled=True,
        supabase_url="https://storage.example",
        supabase_service_role_key=SecretStr("test-key"),
    )
    return settings, pool, store, storage


@pytest.mark.parametrize("extension", ["pdf", "docx"])
@pytest.mark.parametrize("save_fails", [False, True])
def test_content_factory_uses_private_upload_service(
    runtime: tuple[Settings, Mock, Mock, Mock],
    monkeypatch: pytest.MonkeyPatch,
    extension: str,
    save_fails: bool,
) -> None:
    settings, pool, store, storage = runtime
    saved: list[UploadMetadata] = []

    def save(self: TopicsService, metadata: UploadMetadata) -> None:
        saved.append(metadata)
        if save_fails:
            raise RuntimeError("metadata unavailable")

    monkeypatch.setattr(TopicsService, "_save_upload", save)
    if extension == "pdf":
        buffer = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(buffer)
        body = buffer.getvalue()
    else:
        body = docx(
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Nội dung học Python từ tài liệu của người học.</w:t>"
            "</w:r></w:p></w:body></w:document>"
        )
    app = create_content_app(settings, repository=store, gateway=FakeGateway())
    with TestClient(app) as client:
        response = client.post(
            "/uploads",
            files={"file": (f"lesson.{extension}", body)},
            headers={"X-API-Key": settings.api_key, "X-Demo-Upload-Consent": "demo-v1"},
        )
        assert response.status_code == (503 if save_fails else 200)
        schema = client.get("/openapi.json", headers={"X-API-Key": settings.api_key}).json()
        operation_ids = [
            operation["operationId"]
            for path in schema["paths"].values()
            for operation in path.values()
        ]
        assert len(operation_ids) == len(set(operation_ids))
        assert "/tutor/hint" in schema["paths"]
    store.require_schema.assert_called_once()
    pool.close.assert_called_once()
    assert len(saved) == 1
    metadata = saved[0]
    assert metadata.source_uri == f"supabase://uploads/{metadata.id}"
    assert metadata.demo_consent_at is not None
    assert metadata.byte_size == len(body)
    assert metadata.filename == f"lesson.{extension}"
    if save_fails:
        assert storage.removed == metadata.id
    else:
        assert response.json()["upload_id"] == str(metadata.id)


def test_content_factory_closes_pool_when_schema_is_missing(
    runtime: tuple[Settings, Mock, Mock, Mock],
) -> None:
    settings, pool, store, _ = runtime
    store.require_schema.side_effect = ContentUnavailable("P4 schema missing")
    app = create_content_app(settings, repository=store, gateway=FakeGateway())
    with pytest.raises(ContentUnavailable, match="schema missing"), TestClient(app):
        pass
    pool.close.assert_called_once()


@pytest.mark.parametrize("trusted_callback", [False, True])
def test_content_factory_preserves_confirmation_gate(
    runtime: tuple[Settings, Mock, Mock, Mock], trusted_callback: bool
) -> None:
    settings, _, store, _ = runtime
    connection = Mock()
    store.transaction.side_effect = lambda: nullcontext(connection)
    store._subject.return_value = uuid4()
    graph = topic()[2]
    store.graph.return_value = graph
    confirmation = Mock(return_value=False) if trusted_callback else None
    app = create_content_app(
        settings, repository=store, gateway=FakeGateway(), confirmation=confirmation
    )
    learner = str(uuid4())
    with TestClient(app) as client:
        response = client.post(
            "/placement/next",
            json={"learner_id": learner, "subject": "python"},
            headers={"X-API-Key": settings.api_key},
        )
        assert response.status_code == 409
    if confirmation is not None:
        confirmation.assert_called_once_with(learner, "python", graph_revision(graph))


def test_content_factory_keeps_auth_and_demo_consent_checks(
    runtime: tuple[Settings, Mock, Mock, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, _, store, _ = runtime
    save = Mock()
    monkeypatch.setattr(TopicsService, "_save_upload", save)
    app = create_content_app(settings, repository=store, gateway=FakeGateway())
    with TestClient(app) as client:
        assert client.post("/uploads").status_code == 401
        assert client.post("/uploads", headers={"X-API-Key": settings.api_key}).status_code == 403
    save.assert_not_called()


def test_content_factory_persists_upload_and_queues_job_in_sql(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real SQL and P4 schema; object storage and document parsing are fakes."""
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        api_key="test-key",
        demo_uploads_enabled=True,
        supabase_url="https://storage.example",
        supabase_service_role_key=SecretStr("test-key"),
    )

    class Storage:
        async def put(self, upload_id: UUID, body: bytes, media_type: str) -> str:
            return f"supabase://uploads/{upload_id}"

        async def remove(self, upload_id: UUID) -> None:
            raise AssertionError("successful writes must not be removed")

    monkeypatch.setattr("app.main.SupabaseStorage", lambda *args: Storage())
    monkeypatch.setattr(
        "app.api.topics.read_file",
        lambda *args: Document("", (Page(1, "Nội dung Python."),), True, "application/pdf"),
    )
    app = create_content_app(settings, gateway=FakeGateway())
    headers = {"X-API-Key": settings.api_key, "X-Demo-Upload-Consent": "demo-v1"}
    with TestClient(app) as client:
        response = client.post(
            "/uploads", files={"file": ("lesson.pdf", b"synthetic PDF")}, headers=headers
        )
        assert response.status_code == 200, response.text
        upload = response.json()["upload_id"]
        queued = client.post(
            "/topics",
            json={"upload_id": upload, "mode": "quick", "tier": "free"},
            headers=headers,
        )
        assert queued.status_code == 200, queued.text
        with app.state.pool.connection() as connection:
            try:
                assert connection.execute(
                    "select source_uri,demo_consent_at is not null from uploads where id=%s",
                    (UUID(upload),),
                ).fetchone() == (f"supabase://uploads/{upload}", True)
                assert connection.execute(
                    "select upload_id,mode,status from topic_jobs where id=%s",
                    (UUID(queued.json()["topic_id"]),),
                ).fetchone() == (UUID(upload), "quick", "queued")
            finally:
                connection.execute(
                    "delete from topic_jobs where id=%s", (UUID(queued.json()["topic_id"]),)
                )
                connection.execute("delete from uploads where id=%s", (UUID(upload),))
    # The factory-created pool was closed, while the throwaway SQL database remains usable.
    assert app.state.pool.closed
    with create_pool(database_url) as pool:
        Repository(lambda: pool).require_schema()
