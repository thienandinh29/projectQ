import pytest

from tests.api.conftest import Harness


def test_graph_alias_and_required_query(harness: Harness) -> None:
    response = harness.client.get("/graph", params={"learner_id": "u1", "subject": "biology"})
    assert response.status_code == 200
    assert response.json()["edges"] == [{"from": "cells", "to": "photosynthesis"}]
    assert harness.client.get("/graph", params={"subject": "biology"}).status_code == 422


@pytest.mark.parametrize("path", ["/placement/next", "/next-item"])
def test_only_safe_item_fields_are_returned(harness: Harness, path: str) -> None:
    if path == "/placement/next":
        response = harness.client.post(path, json={"learner_id": "u1", "subject": "biology"})
    else:
        response = harness.client.get(path, params={"learner_id": "u1", "subject": "biology"})
    assert response.status_code == 200
    item = response.json()["item"]
    assert set(item) == {"id", "kind", "prompt_vi", "options"}
    assert all(set(option) == {"label"} for option in item["options"])


def test_placement_completion_keeps_null_item(harness: Harness) -> None:
    harness.backend.done = True
    response = harness.client.post(
        "/placement/next", json={"learner_id": "u1", "subject": "biology"}
    )
    assert response.status_code == 200
    assert response.json()["item"] is None
    assert response.json()["done"]
    assert response.json()["gap_slug"] == "photosynthesis"


@pytest.mark.parametrize("path", ["/placement/next", "/next-item", "/attempts"])
def test_unverified_items_never_served_or_persisted(harness: Harness, path: str) -> None:
    assert harness.backend.item is not None
    harness.backend.item = harness.backend.item.model_copy(update={"status": "needs_review"})
    if path == "/next-item":
        response = harness.client.get(path, params={"learner_id": "u1", "subject": "biology"})
    elif path == "/attempts":
        response = harness.client.post(
            path, json={"learner_id": "u1", "item_id": "q1", "answer": 0, "hints_used": 0}
        )
    else:
        response = harness.client.post(path, json={"learner_id": "u1", "subject": "biology"})
    assert response.status_code == 503
    assert not harness.backend.attempts


def test_correct_grade_comes_from_key_and_clears_wrong_answer_feedback(
    harness: Harness,
) -> None:
    response = harness.client.post(
        "/attempts",
        json={
            "learner_id": "u1",
            "item_id": "q1",
            "answer": 0,
            "hints_used": 0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["correct"] is True
    assert "misconception_vi" not in data and "remediation" not in data
    assert data["traces"] and data["p_known"] == 0.4
    assert harness.backend.attempts[0][1].correct


def test_wrong_grade_passes_misconception_to_engine_adapter(harness: Harness) -> None:
    response = harness.client.post(
        "/attempts",
        json={
            "learner_id": "u1",
            "item_id": "q1",
            "answer": 1,
            "hints_used": 2,
        },
    )
    assert response.status_code == 200
    assert not response.json()["correct"]
    request, result = harness.backend.attempts[0]
    assert result.misconception == "oxygen-from-co2" and request.hints_used == 2
    assert response.json()["remediation"]["concept_slug"] == "water"


@pytest.mark.parametrize("answer", [-1, 50, True, None, {"correct": True}, 0.5, "0", "Water"])
def test_invalid_answer_does_not_write_attempt(harness: Harness, answer: object) -> None:
    response = harness.client.post(
        "/attempts",
        json={
            "learner_id": "u1",
            "item_id": "q1",
            "answer": answer,
            "hints_used": 0,
        },
    )
    assert response.status_code == 422
    assert not harness.backend.attempts


def test_missing_item_returns_404(harness: Harness) -> None:
    response = harness.client.post(
        "/attempts",
        json={
            "learner_id": "u1",
            "item_id": "missing",
            "answer": 0,
            "hints_used": 0,
        },
    )
    assert response.status_code == 404
    assert not harness.backend.attempts


def test_reviews_and_exam_plan(harness: Harness) -> None:
    reviews = harness.client.get("/reviews/due", params={"learner_id": "u1"})
    assert reviews.status_code == 200 and reviews.json()["cards"][0]["due_at"]
    plan = harness.client.post(
        "/exam-plan",
        json={
            "learner_id": "u1",
            "subject": "biology",
            "exam_date": "2026-12-01",
        },
    )
    assert plan.status_code == 200 and plan.json()["days"][0]["minutes"] == 20


def test_backend_item_id_mismatch_cannot_grade_another_question(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.graders.mcq import Item

    async def mismatched(item_id: str) -> Item | None:
        assert harness.backend.item is not None
        return harness.backend.item.model_copy(update={"id": "other-question"})

    monkeypatch.setattr(harness.backend, "get_item", mismatched)
    response = harness.client.post(
        "/attempts",
        json={
            "learner_id": "u1",
            "item_id": "q1",
            "answer": 0,
            "hints_used": 0,
        },
    )
    assert response.status_code == 503 and not harness.backend.attempts
