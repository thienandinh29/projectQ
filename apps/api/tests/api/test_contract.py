import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import learn, topics, tutor
from tests.api.conftest import Harness


@pytest.mark.parametrize(
    "path,body",
    [
        ("/topics", {"goal_vi": "Python", "mode": "quick", "tier": "free"}),
        ("/uploads", {"url": "https://books.example/file"}),
        ("/placement/next", {"learner_id": "u1", "subject": "biology"}),
        ("/attempts", {"learner_id": "u1", "item_id": "q1", "answer": 0, "hints_used": 0}),
        ("/tutor/hint", {"learner_id": "u1", "item_id": "q1", "level": 1, "tier": "free"}),
        ("/ask", {"question": "Học gì?", "subject": "biology", "tier": "free"}),
        ("/exam-plan", {"learner_id": "u1", "subject": "biology", "exam_date": "2026-12-01"}),
    ],
)
def test_unconfigured_backend_returns_503(path: str, body: dict[str, object]) -> None:
    app = FastAPI()
    for factory in (learn.create_router, tutor.create_router):
        app.include_router(factory())
    app.include_router(topics.create_router(demo_uploads_enabled=True))
    with TestClient(app) as client:
        response = client.post(path, json=body, headers={"X-Demo-Upload-Consent": "demo-v1"})
        assert response.status_code == 503
        assert "item" not in response.json()


@pytest.mark.parametrize("path", ["/graph", "/next-item", "/reviews/due"])
def test_unconfigured_get_backend_returns_503(path: str) -> None:
    app = FastAPI()
    app.include_router(learn.create_router())
    with TestClient(app) as client:
        response = client.get(path, params={"learner_id": "u1", "subject": "biology"})
        assert response.status_code == 503


def test_openapi_exposes_ten_p3_routes_and_both_upload_encodings(harness: Harness) -> None:
    schema = harness.client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/topics",
        "/uploads",
        "/graph",
        "/placement/next",
        "/attempts",
        "/next-item",
        "/tutor/hint",
        "/ask",
        "/reviews/due",
        "/exam-plan",
    }
    content = schema["paths"]["/uploads"]["post"]["requestBody"]["content"]
    assert set(content) == {"application/json", "multipart/form-data"}
    learner = schema["components"]["schemas"]["PublicOption"]["properties"]
    assert set(learner) == {"label"}


def test_client_cannot_inject_grade_or_mastery(harness: Harness) -> None:
    response = harness.client.post(
        "/attempts",
        json={
            "learner_id": "u1",
            "item_id": "q1",
            "answer": 1,
            "hints_used": 0,
            "correct": True,
            "p_known": 1,
        },
    )
    assert response.status_code == 422
    assert not harness.backend.attempts


def test_preview_is_explicitly_labelled_as_fixture_only() -> None:
    from tests.api.preview import app

    with TestClient(app) as client:
        response = client.get("/openapi.json")
        assert response.headers["X-NodeTrail-Backend"] == "fixture"
        assert "fixture" in response.json()["info"]["title"]
