"""Offline comparison with the pushed P1 contract, without changing P1-owned files.

Git blobs are read locally at a pinned revision; no fetch or network occurs in tests.
A shallow checkout lacking that revision skips this extra comparison explicitly.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import BaseModel

from app.api import learn, topics, tutor
from app.research.library import Book, _export_p1

P1_REVISION = "5245e56"
ROOT = Path(__file__).resolve().parents[4]


def blob(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{P1_REVISION}:{path}"],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        pytest.skip(f"P1 contract revision {P1_REVISION} unavailable locally")
    return result.stdout


@pytest.fixture
def contracts(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    # The reference schema imports only its trace contract; isolate both modules.
    for name, path in (
        ("app.engine.trace", "apps/api/app/engine/trace.py"),
        ("_p1_reference_contracts", "apps/api/app/schemas.py"),
    ):
        module = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, module)
        exec(compile(blob(path), path, "exec"), module.__dict__)
    return module


@pytest.mark.parametrize(
    "filename,local,shared",
    [
        ("topics.request", topics.TopicInput, "TopicCreate"),
        ("topics.response", topics.TopicResponse, "TopicCreated"),
        ("uploads.response", topics.UploadResponse, "UploadCreated"),
        ("placement-next.request", learn.LearnerSubject, "PlacementRequest"),
        ("placement-next.question", learn.PlacementResponse, "PlacementStep"),
        ("placement-next.done", learn.PlacementResponse, "PlacementStep"),
        ("next-item.response", learn.NextResponse, "NextItem"),
        ("graph.response", learn.GraphResponse, "GraphView"),
        ("attempts.request", learn.AttemptInput, "AttemptCreate"),
        ("attempts.correct", learn.AttemptResponse, "AttemptResult"),
        ("attempts.wrong", learn.AttemptResponse, "AttemptResult"),
        ("tutor-hint.request", tutor.HintInput, "HintRequest"),
        ("tutor-hint.response", tutor.HintResponse, "HintResponse"),
        ("ask.request", tutor.AskInput, "AskRequest"),
        ("ask.response", tutor.AskResponse, "AskResponse"),
        ("reviews-due.response", learn.ReviewsResponse, "DueReviews"),
        ("exam-plan.request", learn.ExamInput, "ExamPlanRequest"),
        ("exam-plan.response", learn.ExamResponse, "ExamPlan"),
    ],
)
def test_p1_mock_round_trip(
    contracts: ModuleType, filename: str, local: type[BaseModel], shared: str
) -> None:
    original = json.loads(blob(f"specs/contracts/mocks/{filename}.json"))
    reference = getattr(contracts, shared)
    canonical = reference.model_validate(original)
    adapted = local.model_validate(canonical.model_dump(mode="json", by_alias=True))
    reference.model_validate(adapted.model_dump(mode="json", by_alias=True))


def test_library_exports_validate_against_p1(contracts: ModuleType, tmp_path: Path) -> None:
    book = Book(
        slug="biology",
        title="Biology",
        publisher="LibreTexts",
        start_url="https://bio.libretexts.org/book",
        license_url="https://bio.libretexts.org/book",
        page_prefix="https://bio.libretexts.org/book",
    )
    _export_p1(
        book,
        tmp_path,
        [
            {
                "source_uri": "https://bio.libretexts.org/book/1",
                "sha256": "abc",
                "license": "CC BY-SA 4.0",
                "text": "A cited passage.",
            }
        ],
    )
    contracts.SourceMeta.model_validate_json((tmp_path / "source.json").read_bytes())
    contracts.ParsedDocument.model_validate_json((tmp_path / "document.json").read_bytes())


def test_routes_with_actual_p1_engine_and_memory_storage(
    contracts: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real P1 decisions through HTTP; persistence remains in memory, not H7 acceptance."""
    from datetime import UTC, datetime

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.graders.mcq import Grade, Item
    from tests.api.conftest import FakeBackend

    monkeypatch.setitem(sys.modules, "app.schemas", contracts)
    engines = {}
    for part in ("bkt", "graph", "placement", "remediation", "path"):
        name = "app.engine." + part
        module = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, module)
        path = f"apps/api/app/engine/{part}.py"
        exec(compile(blob(path), path, "exec"), module.__dict__)
        engines[part] = module
    graph = engines["graph"].Graph.from_edges(
        ["water", "photosynthesis"], [("water", "photosynthesis")]
    )
    now = datetime.now(UTC)
    mastery = {"water": 0.2, "photosynthesis": 0.2}
    bkt = engines["bkt"]

    class Backend(FakeBackend):
        async def placement(self, request: learn.LearnerSubject) -> learn.PlacementSelection:
            slug, trace = engines["placement"].next_question(graph, [], now=now)
            assert slug == "photosynthesis"
            return learn.PlacementSelection(
                item=self.item,
                done=False,
                trace=learn.DecisionTrace.model_validate(trace.model_dump()),
            )

        async def apply_attempt(
            self, request: learn.AttemptInput, item: Item, result: Grade
        ) -> learn.AttemptUpdate:
            value, trace = bkt.update_traced(
                mastery["photosynthesis"],
                result.correct,
                bkt.DEFAULT_PARAMS["mcq"],
                concept_slug="photosynthesis",
                now=now,
                item_id=item.id,
                misconception=result.misconception,
            )
            mastery["photosynthesis"] = value
            plan, root_trace = engines["remediation"].remediate(
                graph,
                mastery,
                "photosynthesis",
                now=now,
                item_id=item.id,
                misconception=result.misconception,
            )
            return learn.AttemptUpdate.model_validate(
                {
                    "p_known": value,
                    "mastered": bkt.is_mastered(value),
                    "remediation": plan.to_contract().model_dump(),
                    "traces": [trace.model_dump(), root_trace.model_dump()],
                }
            )

        async def next_item(self, learner_id: str, subject: str) -> learn.NextSelection:
            step, _ = engines["path"].next_step(
                graph, mastery, now=now, resume_origin="photosynthesis"
            )
            assert step.concept_slug == "water"
            assert self.item is not None
            return learn.NextSelection(
                item=self.item.model_copy(update={"id": "water-question"}), reason_vi=step.reason_vi
            )

    app = FastAPI()
    app.include_router(learn.create_router(Backend()))
    with TestClient(app) as client:
        placement = client.post("/placement/next", json={"learner_id": "u1", "subject": "biology"})
        assert placement.status_code == 200
        contracts.PlacementStep.model_validate(placement.json())
        result = client.post("/attempts", json={"learner_id": "u1", "item_id": "q1", "answer": 1})
        assert result.status_code == 200
        canonical = contracts.AttemptResult.model_validate(result.json())
        assert canonical.correct is False and canonical.p_known < 0.2
        assert canonical.remediation.concept_slug == "water"
        assert [trace.kind for trace in canonical.traces] == ["bkt_update", "root_cause"]
        response = client.get("/next-item", params={"learner_id": "u1", "subject": "biology"})
        assert response.status_code == 200 and response.json()["item"]["id"] == "water-question"
        contracts.NextItem.model_validate(response.json())
