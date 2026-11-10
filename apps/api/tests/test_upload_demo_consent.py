import asyncio
from collections.abc import Sequence
from uuid import uuid4

import pytest

from app.content.ports import ContentPorts
from app.content.repository import ContentUnavailable, Repository
from app.db import create_pool
from app.research.agent import ChosenSource
from app.services.topics import TopicsService
from app.uploads.reader import Document, Page
from tests.content.fakes import FakeGateway


class TestVectors:
    dim = 1024

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1023 for _ in texts]


@pytest.mark.parametrize("demo_enabled", [False, True])
@pytest.mark.parametrize("accepted", [False, True])
def test_worker_requires_demo_mode_and_persisted_consent(
    database_url: str, demo_enabled: bool, accepted: bool
) -> None:
    document = Document(
        f"https://books.example/{uuid4()}", (Page(1, "Public demo material."),), True
    )
    with create_pool(database_url) as pool:
        service = TopicsService(lambda: pool)
        upload_id = asyncio.run(service.persist_upload(document, None, None, demo_consent=accepted))
        with pool.connection() as conn:
            row = conn.execute(
                "select demo_consent_at from uploads where id=%s", (upload_id,)
            ).fetchone()
            assert row and (row[0] is not None) == accepted
        ports = ContentPorts(
            Repository(lambda: pool),
            FakeGateway(),
            "demo-consent-test",
            upload_model_permission=demo_enabled,
        )
        if accepted and demo_enabled:
            assert asyncio.run(ports.load_upload(upload_id)) == document
        else:
            with pytest.raises(ContentUnavailable, match="consent"):
                asyncio.run(ports.load_upload(upload_id))


@pytest.mark.parametrize("subject", ["topic-", "user-upload-"])
def test_upload_material_never_becomes_a_curated_source(database_url: str, subject: str) -> None:
    uri = f"https://books.example/{uuid4()}"
    document = Document(
        uri, (Page(1, "PRIVATE DEMO SENTINEL synthetic review data. " * 100),), True
    )
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        demo = ContentPorts(
            repo,
            FakeGateway(),
            subject + uuid4().hex,
            upload_model_permission=True,
            embedder=TestVectors(),
        )
        asyncio.run(demo.index([], document))
        ordinary = ContentPorts(
            repo, FakeGateway(), "public-fallback-" + uuid4().hex, embedder=TestVectors()
        )
        assert not asyncio.run(ordinary.quick_sources("topic user upload"))
        public = ChosenSource(
            title="Public source",
            publisher="Public publisher",
            url=uri,
            license="CC BY 4.0",
            text="Public fallback source content. " * 100,
        )
        prepared = asyncio.run(ordinary.index([public], None))
        assert prepared and all("PRIVATE DEMO SENTINEL" not in c.text for c in prepared)
