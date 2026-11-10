"""Real SQL/engine wiring; search, pages, models and vectors are controlled fixtures."""

import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.content.gateway import ModelReply
from app.content.models import Chunk, ModelIdentity, Source
from app.content.ports import ContentPorts, process_claimed_job
from app.content.repository import ContentUnavailable, Repository
from app.db import create_pool
from app.jobs.worker import run_once
from app.main import create_content_app
from app.rag.retrieve import Retriever
from app.research.agent import ChosenSource, ResearchAgent
from app.research.reader import Allowlist, Publisher, SafeReader
from app.research.relevance import ResearchRelevance
from app.research.runtime import research_scope
from app.research.search import BraveSearch, TavilySearch
from app.schemas import Citation
from app.uploads.reader import Document, Page
from tests.content.test_runtime_database import database_url as database_url


class Vectors:
    dim = 1024

    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.fail_on: int | None = None

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        if self.fail_on == len(self.batches):
            raise RuntimeError("controlled embedding failure")
        return [[1.0] + [0.0] * 1023 for _ in texts]


def test_downloaded_pdf_keeps_each_page_and_license_origin(database_url: str) -> None:
    docs = pages()
    pdf_pages = (
        Page(1, "First derivative lesson page. " * 8),
        Page(2, "Second derivative lesson page. " * 8),
    )
    docs[0] = replace(
        docs[0],
        url="https://a.example/lesson.pdf",
        text="\n".join(p.text for p in pdf_pages),
        pages=pdf_pages,
        license_source_url="https://a.example/resource",
    )
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        ports = ContentPorts(repo, DeepModels(), "topic-" + uuid4().hex, embedder=Vectors())
        prepared = asyncio.run(ports.index(docs, None))
        selected = [c for c in prepared if c.source_uri == docs[0].url]
        assert {c.page for c in selected} == {1, 2}
        assert all("Second derivative" not in c.text for c in selected if c.page == 1)
        assert all("First derivative" not in c.text for c in selected if c.page == 2)
        assert "https://a.example/resource" in ports.sources[0].attribution


def pages() -> list[ChosenSource]:
    return [
        ChosenSource(
            f"New lesson {n}",
            "Publisher A" if n < 2 else "Publisher B",
            f"https://{'a' if n < 2 else 'b'}.example/{n}",
            "CC BY 4.0",
            f"New source rule {n}. This is a complete educational explanation of the rule. "
            "It applies only to this lesson and supplies evidence for its question. CC BY 4.0",
        )
        for n in range(3)
    ]


def test_new_pages_embed_all_sources_and_reuse_unchanged_vectors(database_url: str) -> None:
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        vectors = Vectors()
        docs = pages()
        # A URL is already present in another subject; Deep must still ingest all fresh pages.
        old = Source(
            source_id=docs[0].url,
            title="Old library copy",
            author="",
            publisher="A",
            version="old",
            url=docs[0].url,
            section="Old",
            license="CC BY 4.0",
            accessed_at="2026-11-08",
            attribution="A",
            model_ingestion_allowed=True,
        )
        repo.save_material(
            "old-library",
            [old],
            [
                Chunk(
                    chunk_id=uuid4(),
                    source_id=old.source_id,
                    section="Old",
                    content="Stale library text",
                    representation="verbatim",
                    license=old.license,
                )
            ],
        )
        ports = ContentPorts(repo, DeepModels(), "deep-pages", embedder=vectors)
        prepared = asyncio.run(ports.index(docs, None))
        assert len(prepared) == 3 and len(vectors.batches) == 1
        assert {p.source_uri for p in prepared} == {d.url for d in docs}
        assert all("Stale" not in p.text for p in prepared)
        with repo.transaction() as conn:
            assert conn.execute(
                "select count(*) from chunks where id=any(%s) and embedding is not null",
                ([UUID(p.id) for p in prepared],),
            ).fetchone() == (3,)
        assert asyncio.run(ports.index(docs, None)) == prepared
        assert len(vectors.batches) == 1
        changed = [
            ports.chunks[0].model_copy(update={"content": "Changed source content"}),
            *ports.chunks[1:],
        ]
        repo.save_material("deep-pages", ports.sources, changed)
        with repo.transaction() as conn:
            assert conn.execute(
                "select embedding is null from chunks where id=%s", (changed[0].chunk_id,)
            ).fetchone() == (True,)
            assert conn.execute(
                "select count(*) from chunks where id=any(%s) and embedding is not null",
                ([c.chunk_id for c in changed[1:]],),
            ).fetchone() == (2,)


def test_embedding_batches_resume_and_reject_stale_writes(database_url: str) -> None:
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        doc = pages()[0]
        source = Source(
            source_id=doc.url,
            title="Batch fixture",
            author="",
            publisher="A",
            version="test",
            url=doc.url,
            section="Rules",
            license=doc.license,
            accessed_at="2026-11-08",
            attribution="A",
            model_ingestion_allowed=True,
        )
        chunks = [
            Chunk(
                chunk_id=uuid4(),
                source_id=source.source_id,
                section="Rules",
                content=f"Rule {n}",
                representation="verbatim",
                license=source.license,
            )
            for n in range(35)
        ]
        repo.save_material("batch-deep", [source], chunks)
        vectors = Vectors()
        vectors.fail_on = 2
        ports = ContentPorts(repo, DeepModels(), "batch-deep", embedder=vectors)
        ports.sources, ports.chunks = [source], chunks
        with pytest.raises(RuntimeError):
            asyncio.run(ports._embed_material())
        with repo.transaction() as conn:
            assert conn.execute(
                "select count(*) from chunks where id=any(%s) and embedding is not null",
                ([c.chunk_id for c in chunks],),
            ).fetchone() == (32,)
        vectors.fail_on = None
        asyncio.run(ports._embed_material())
        assert len(vectors.batches[-1]) == 3

        class Changed(Vectors):
            async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
                with repo.transaction() as conn:
                    conn.execute(
                        "update chunks set content='Changed during embedding',embedding=null "
                        "where id=%s",
                        (chunks[0].chunk_id,),
                    )
                return await super().aembed(texts)

        with repo.transaction() as conn:
            conn.execute("update chunks set embedding=null where id=%s", (chunks[0].chunk_id,))
        ports.embedder = Changed()
        with pytest.raises(ContentUnavailable):
            asyncio.run(ports._embed_material())
        with repo.transaction() as conn:
            assert conn.execute(
                "select embedding is null from chunks where id=%s", (chunks[0].chunk_id,)
            ).fetchone() == (True,)


def test_deep_upload_keeps_web_sources_and_scopes_reused_upload_ids(database_url: str) -> None:
    document = Document(
        "supabase://uploads/deep-fixture", (Page(1, "Uploaded teaching rule."),), True
    )
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        all_ids = []
        for subject in ["uploaded-deep-a", "uploaded-deep-b"]:
            vectors = Vectors()
            ports = ContentPorts(
                repo, DeepModels(), subject, embedder=vectors, upload_model_permission=True
            )
            prepared = asyncio.run(ports.index(pages(), document))
            assert len(prepared) == 4
            assert {p.source_uri for p in prepared} == {
                document.source_uri,
                *(p.url for p in pages()),
            }
            assert sum(len(batch) for batch in vectors.batches) == 4
            all_ids.append({p.id for p in prepared})
        assert all_ids[0].isdisjoint(all_ids[1])


class DeepModels:
    """Fixture model identities; never real verification or educational validation."""

    async def generate(self, **kwargs: Any) -> ModelReply:
        task, payload = kwargs["task"], kwargs["payload"]
        identity = ModelIdentity(
            provider="test-only",
            model="fixture-generator",
            family="deepseek",
            identity_source="gateway",
        )
        content: dict[str, Any]
        if task == "plan_research":
            content = {"query": "source rule lesson", "scope_vi": "Fixture scope"}
        elif task == "assess_research_plan":
            content = {"preserves_goal": True, "reason_vi": "Fixture scope matches"}
        elif task == "assess_research_source":
            if "candidates" in payload:
                content = {"urls": [r["url"] for r in payload["candidates"]]}
            else:
                content = {
                    "teaches_goal": True,
                    "reason_vi": "Fixture lesson",
                    "teaching_excerpt_id": payload["excerpts"][0]["id"],
                }
        elif task == "extract_graph":
            ids = re.findall(
                r'\[CHUNK id="([a-f0-9-]+)" source_id="[^"]+"\]', payload["source_data"]
            )
            sources = payload["sources"]
            assert len(ids) == 3 and len(sources) == 3
            graph = {
                "concepts": [
                    {
                        "slug": f"new-rule-{n}",
                        "name_vi": f"Rule {n}",
                        "name_en": f"Rule {n}",
                        "description_vi": "Fixture source rule",
                        "sources": [sources[n]["url"]],
                        "chunk_ids": [key],
                    }
                    for n, key in enumerate(ids)
                ],
                "edges": [],
            }
            content = {"relevant_to_goal": True, "graph": graph, "reason_vi": "Fixture only"}
        elif task == "generate_items":
            concepts = payload["graph"]["concepts"]
            content = {"items": []}
            for n in range(payload["count"]):
                concept = concepts[n % len(concepts)]
                content["items"].append(
                    {
                        "id": f"draft-{n}",
                        "concept": concept["slug"],
                        "difficulty": 0.4,
                        "prompt_vi": f"Fixture question {n} about {concept['name_vi']}?",
                        "source": concept["sources"][0],
                        "source_ids": [concept["sources"][0]],
                        "chunk_ids": concept["chunk_ids"],
                        "answer_id": "right",
                        "options": [
                            {
                                "id": "right",
                                "label": "Supported rule",
                                "correct": True,
                                "misconception": None,
                            },
                            {
                                "id": "wrong",
                                "label": "Unrelated rule",
                                "correct": False,
                                "misconception": "wrong-rule",
                            },
                        ],
                        "misconceptions": [
                            {"slug": "wrong-rule", "description_vi": f"Wrong rule {n}"}
                        ],
                        "explanation_vi": "Fixture source evidence",
                    }
                )
        elif task == "verify_item":
            assert set(payload) == {"question", "options", "chunks"}
            chunk = payload["chunks"][0]
            content = {
                "supported": True,
                "selected_option_id": "choice-0",
                "unique_answer": True,
                "ambiguous": False,
                "multiple_correct": False,
                "insufficient_evidence": False,
                "evidence": [{"chunk_id": chunk["chunk_id"], "quote": chunk["content"]}],
                "reason": "Controlled fixture only",
            }
            identity = identity.model_copy(update={"model": "fixture-verifier", "family": "gemini"})
        else:
            raise AssertionError(task)
        return ModelReply(content=content, identity=identity)


@pytest.mark.parametrize("provider", ["brave", "tavily"])
def test_deep_http_worker_to_graph_and_learning(database_url: str, provider: str) -> None:
    docs = pages()
    allowlist = Allowlist(
        publishers=[
            Publisher(name="Publisher A", domains=["a.example"]),
            Publisher(name="Publisher B", domains=["b.example"]),
        ]
    )

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    def search_response(request: httpx.Request) -> httpx.Response:
        if provider == "tavily":
            host = json.loads(request.content)["include_domains"][0]
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"title": doc.title, "url": doc.url} for doc in docs if host in doc.url
                    ]
                },
            )
        host = "a.example" if "site:a.example" in request.url.params["q"] else "b.example"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"title": doc.title, "url": doc.url} for doc in docs if host in doc.url
                    ]
                }
            },
        )

    def read_response(request: httpx.Request) -> httpx.Response:
        url = "https://" + request.headers["host"] + request.url.path
        doc = next(d for d in docs if d.url == url)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<p>{doc.text}</p>")

    reader = SafeReader(
        allowlist=allowlist, resolver=resolve, transport=httpx.MockTransport(read_response)
    )
    agent = ResearchAgent(
        (TavilySearch if provider == "tavily" else BraveSearch)(
            "test-search-key", transport=httpx.MockTransport(search_response)
        ),
        allowlist=allowlist,
        reader=reader,
        relevance=ResearchRelevance(DeepModels()),
    )
    with create_pool(database_url) as pool:
        repo, vectors, models = Repository(lambda: pool), Vectors(), DeepModels()
        queries: list[str] = []

        class RecordingRetriever:
            async def search(self, query: str, subject: str, k: int = 5) -> list[Citation]:
                queries.append(query)
                return await Retriever(pool, vectors).search(query, subject, k)

        app = create_content_app(
            Settings(_env_file=None, database_url=database_url, api_key="test-api"),
            repository=repo,
            gateway=models,
        )
        with TestClient(app, headers={"X-API-Key": "test-api"}) as client:
            created = client.post(
                "/topics",
                json={
                    "goal_vi": f"A new subject outside the library via {provider}",
                    "mode": "deep",
                    "tier": "pro",
                },
            )
            assert created.status_code == 200
            job = created.json()["topic_id"]

            def process(row: dict[str, Any]) -> None:
                with research_scope(agent):
                    asyncio.run(
                        process_claimed_job(
                            repo,
                            models,
                            row,
                            retriever=RecordingRetriever(),
                            retrieval_subject="auto",
                            embedder=vectors,
                        )
                    )

            assert run_once(database_url, processor=process)
            assert queries == ["source rule lesson"]
            state = client.get(f"/topics/{job}").json()
            assert state["status"] == "ready" and state["items_ready"]
            assert len(state["sources"]) == 3
            assert {e["kind"] for e in state["trail"]} == {"search", "read", "select"}
            subject = state["subject_slug"]
            with repo.transaction() as conn:
                assert len(repo.item_ids(conn, subject)) == 6
                assert conn.execute(
                    "select count(*) from chunks c join sources s on s.id=c.source_id "
                    "join subjects b on b.id=s.subject_id where b.slug=%s "
                    "and c.embedding is not null",
                    (subject,),
                ).fetchone() == (3,)
            learner = client.post(
                "/learners", json={"display_name": "Deep fixture learner"}
            ).json()["learner_id"]
            scope = {"learner_id": learner, "subject": subject}
            published = client.get("/graph/review", params={"subject": subject}).json()
            for draft_status in ("graph", "failed"):
                with repo.transaction() as conn:
                    conn.execute(
                        "update topic_jobs set status=%s,graph_ready=false,items_ready=false "
                        "where id=%s",
                        (draft_status, job),
                    )
                assert client.get("/graph/review", params={"subject": subject}).status_code == 409
                assert client.get("/graph", params=scope).status_code == 409
                assert (
                    client.post(
                        "/graph/confirm",
                        json={k: published[k] for k in ["subject", "graph_revision"]},
                    ).status_code
                    == 409
                )
                assert client.post("/placement/next", json=scope).status_code == 409
                with repo.transaction() as conn:
                    assert conn.execute(
                        "select count(*) from learner_graph_confirmations where learner_id=%s",
                        (learner,),
                    ).fetchone() == (0,)
            with repo.transaction() as conn:
                conn.execute(
                    "update topic_jobs set status='ready',graph_ready=true,items_ready=true "
                    "where id=%s",
                    (job,),
                )
            assert client.post("/placement/next", json=scope).status_code == 409
            review = client.get("/graph/review", params={"subject": subject}).json()
            assert not review["confirmed"]
            assert (
                client.post(
                    "/graph/confirm", json={k: review[k] for k in ["subject", "graph_revision"]}
                ).status_code
                == 200
            )
            step = client.post("/placement/next", json=scope)
            assert step.status_code == 200
            public = step.json()["item"]
            assert set(public) == {"id", "kind", "prompt_vi", "options"}
            graded = client.post(
                "/attempts",
                json={"learner_id": learner, "item_id": public["id"], "answer": 0, "hints_used": 0},
            )
            assert graded.status_code == 200 and graded.json()["correct"]
            with repo.transaction() as conn:
                assert conn.execute(
                    "select count(*) from attempts where learner_id=%s", (learner,)
                ).fetchone() == (1,)
                assert conn.execute(
                    "select p_known from mastery where learner_id=%s", (learner,)
                ).fetchone()[0] == pytest.approx(graded.json()["p_known"])  # type: ignore[index]
