from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.config import Settings
from app.engine import bkt
from app.main import create_app


@pytest.fixture
def learning_data(database_url: str) -> tuple[str, str, str]:
    subject = "integration-" + uuid4().hex
    item_id = "item-" + uuid4().hex
    payload = {
        "id": item_id,
        "kind": "mcq",
        "prompt_vi": "Chọn đáp án đúng",
        "difficulty": 0.5,
        "source": "https://example.org/source",
        "chunk_ids": [str(uuid4())],
        "status": "verified",
        "options": [
            {"label": "Đúng", "correct": True, "misconception": None},
            {"label": "Sai", "correct": False, "misconception": "Nhầm kiến thức nền"},
        ],
    }
    with psycopg.connect(database_url) as conn:
        learner = conn.execute(
            "insert into learners(display_name) values ('Test') returning id"
        ).fetchone()
        row = conn.execute(
            "insert into subjects(slug,name_vi,name_en) values (%s,'Test','Test') returning id",
            (subject,),
        ).fetchone()
        assert learner and row
        concept = conn.execute(
            "insert into concepts(subject_id,slug,name_vi,name_en) "
            "values (%s,'c','C','C') returning id",
            (row[0],),
        ).fetchone()
        assert concept
        conn.execute(
            "insert into items(concept_id,kind,prompt,payload) values (%s,'mcq','?',%s)",
            (concept[0], Jsonb(payload)),
        )
        conn.execute(
            "insert into misconceptions(concept_id,description_vi) "
            "values (%s,'Nhầm kiến thức nền')",
            (concept[0],),
        )
    return str(learner[0]), subject, item_id


def test_real_routes_update_mastery_review_and_audit(
    database_url: str,
    learning_data: tuple[str, str, str],
) -> None:
    learner, subject, item = learning_data
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        query = {"learner_id": learner, "subject": subject}
        graph = client.get("/graph", params=query)
        assert graph.status_code == 200
        assert graph.json()["nodes"][0]["p_known"] == pytest.approx(0.2)
        next_item = client.get("/next-item", params=query).json()["item"]
        assert next_item["id"] == item
        assert set(next_item["options"][0]) == {"label"}
        with psycopg.connect(database_url) as conn:
            conn.execute(
                "insert into decision_traces(learner_id,subject_id,concept_slug,kind,"
                "at,rule,rule_vi) "
                "select %s,id,'c','placement_step',now(),'placement.done.gap','Done' "
                "from subjects where slug=%s",
                (learner, subject),
            )
        body = {"learner_id": learner, "item_id": item, "answer": 1, "hints_used": 0}
        wrong = client.post("/attempts", json=body)
        assert wrong.status_code == 200, wrong.text
        assert not wrong.json()["correct"]
        assert wrong.json()["misconception_vi"] == "Nhầm kiến thức nền"
        assert [t["kind"] for t in wrong.json()["traces"]] == ["bkt_update", "root_cause"]
        prior = wrong.json()["p_known"]
        for _ in range(8):
            response = client.post("/attempts", json={**body, "answer": 0})
            assert response.status_code == 200, response.text
            actual = response.json()
            prior = bkt.update(prior, True, bkt.DEFAULT_PARAMS["mcq"])
            assert actual["p_known"] == pytest.approx(prior)
        assert actual["mastered"]
        assert any(t["kind"] == "review" for t in actual["traces"])
        assert client.get("/graph", params=query).json()["nodes"][0]["mastered"]
        assert client.get("/reviews/due", params={"learner_id": learner}).status_code == 200
        assert (
            client.post(
                "/tutor/hint",
                json={"learner_id": learner, "item_id": item, "level": 1, "tier": "free"},
            ).status_code
            == 503
        )
    with psycopg.connect(database_url) as conn:
        assert conn.execute(
            "select count(*) from attempts where learner_id=%s", (learner,)
        ).fetchone() == (9,)
        assert conn.execute(
            "select count(*) from review_cards where learner_id=%s", (learner,)
        ).fetchone() == (1,)
        count = conn.execute(
            "select count(*) from decision_traces where learner_id=%s and attempt_id is not null",
            (learner,),
        ).fetchone()
        assert count and count[0] >= 10


def test_placement_records_answers_and_finishes_without_reset(
    database_url: str,
    learning_data: tuple[str, str, str],
) -> None:
    learner, subject, item = learning_data
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        body = {"learner_id": learner, "subject": subject}
        first = client.post("/placement/next", json=body)
        assert first.status_code == 200, first.text
        assert first.json()["item"]["id"] == item
        assert not first.json()["done"]
        assert (
            client.post(
                "/attempts",
                json={"learner_id": learner, "item_id": item, "answer": 0, "hints_used": 0},
            ).status_code
            == 200
        )
        done = client.post("/placement/next", json=body)
        assert done.status_code == 200, done.text
        assert done.json()["done"] and done.json()["item"] is None
        before = client.get("/graph", params=body).json()
        assert before["nodes"][0]["p_known"] == pytest.approx(0.85)
        assert client.post("/placement/next", json=body).json()["done"]
        assert client.get("/graph", params=body).json() == before
        assert (
            client.post(
                "/attempts",
                json={"learner_id": learner, "item_id": item, "answer": 0, "hints_used": 0},
            ).status_code
            == 200
        )
        learned = client.get("/graph", params=body).json()
        assert learned != before
        assert client.post("/placement/next", json=body).json()["done"]
        assert client.get("/graph", params=body).json() == learned
    with psycopg.connect(database_url) as conn:
        assert conn.execute(
            "select answer->>'phase' from attempts where learner_id=%s", (learner,)
        ).fetchone() == ("placement",)


def test_attempt_transaction_rolls_back_on_trace_failure(
    database_url: str,
    learning_data: tuple[str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    learner, _, item = learning_data

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr("app.services.backend.save_trace", fail)
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        result = client.post(
            "/attempts", json={"learner_id": learner, "item_id": item, "answer": 0, "hints_used": 0}
        )
        assert result.status_code == 503
    with psycopg.connect(database_url) as conn:
        for table in ("attempts", "mastery", "review_cards"):
            assert conn.execute(
                f"select count(*) from {table} where learner_id=%s", (learner,)
            ).fetchone() == (0,)


def test_concurrent_attempts_preserve_both_updates(
    database_url: str,
    learning_data: tuple[str, str, str],
) -> None:
    learner, _, item = learning_data
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        body = {"learner_id": learner, "item_id": item, "answer": 0, "hints_used": 0}
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: client.post("/attempts", json=body), range(2)))
        assert all(r.status_code == 200 for r in results)
    with psycopg.connect(database_url) as conn:
        actual = conn.execute(
            "select p_known from mastery where learner_id=%s", (learner,)
        ).fetchone()
        expected = bkt.update(
            bkt.update(0.2, True, bkt.DEFAULT_PARAMS["mcq"]), True, bkt.DEFAULT_PARAMS["mcq"]
        )
        assert actual and actual[0] == pytest.approx(expected)


@pytest.mark.parametrize("answer", [True, -1, 2, "Đúng", None])
def test_reject_invalid_answer_without_writes(
    database_url: str,
    learning_data: tuple[str, str, str],
    answer: object,
) -> None:
    learner, _, item = learning_data
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        assert (
            client.post(
                "/attempts",
                json={"learner_id": learner, "item_id": item, "answer": answer, "hints_used": 0},
            ).status_code
            == 422
        )
    with psycopg.connect(database_url) as conn:
        assert conn.execute(
            "select count(*) from attempts where learner_id=%s", (learner,)
        ).fetchone() == (0,)


def test_pending_items_never_served_or_graded(
    database_url: str,
    learning_data: tuple[str, str, str],
) -> None:
    learner, subject, item = learning_data
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "update items set payload=jsonb_set(payload,'{status}',%s) where payload->>'id'=%s",
            (Jsonb("needs_review"), item),
        )
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        assert (
            client.get("/next-item", params={"learner_id": learner, "subject": subject}).status_code
            == 404
        )
        assert (
            client.post(
                "/attempts",
                json={"learner_id": learner, "item_id": item, "answer": 0, "hints_used": 0},
            ).status_code
            == 503
        )
    with psycopg.connect(database_url) as conn:
        assert conn.execute(
            "select count(*) from attempts where learner_id=%s", (learner,)
        ).fetchone() == (0,)


def test_next_item_rotates_unseen_then_oldest(
    database_url: str, learning_data: tuple[str, str, str]
) -> None:
    learner, subject, first = learning_data
    second = "second-" + uuid4().hex
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "select concept_id,payload from items where payload->>'id'=%s", (first,)
        ).fetchone()
        assert row
        payload = {**row[1], "id": second, "difficulty": 0.6}
        conn.execute(
            "insert into items(concept_id,kind,prompt,payload) values (%s,'mcq','?',%s)",
            (row[0], Jsonb(payload)),
        )
        conn.execute(
            "update items set payload=jsonb_set(payload,'{difficulty}','0.3') "
            "where payload->>'id'=%s",
            (first,),
        )
    served = []
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        for _ in range(4):
            response = client.get("/next-item", params={"learner_id": learner, "subject": subject})
            assert response.status_code == 200, response.text
            item = response.json()["item"]["id"]
            served.append(item)
            result = client.post(
                "/attempts", json={"learner_id": learner, "item_id": item, "answer": 1}
            )
            assert result.status_code == 200, result.text
    assert served == [first, second, first, second]


def test_next_item_skips_empty_concept(
    database_url: str, learning_data: tuple[str, str, str]
) -> None:
    learner, subject, item = learning_data
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "insert into concepts(subject_id,slug,name_vi,name_en) "
            "select id,'a-empty','Empty','Empty' from subjects where slug=%s",
            (subject,),
        )
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        response = client.get("/next-item", params={"learner_id": learner, "subject": subject})
        assert response.status_code == 200, response.text
        assert response.json()["item"]["id"] == item


def test_attempt_retries_are_atomic(database_url: str, learning_data: tuple[str, str, str]) -> None:
    learner, _, item = learning_data
    body = {"learner_id": learner, "item_id": item, "answer": 0, "client_attempt_id": str(uuid4())}
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: client.post("/attempts", json=body), range(2)))
        assert all(r.status_code == 200 for r in results)
        assert results[0].json() == results[1].json()
        assert client.post("/attempts", json={**body, "answer": 1}).status_code == 409
        assert client.post("/attempts", json={**body, "hints_used": 1}).status_code == 409
        with psycopg.connect(database_url) as conn:
            row = conn.execute(
                "select payload from items where payload->>'id'=%s", (item,)
            ).fetchone()
            assert row
            payload = row[0]
            payload["options"] = [
                {"label": "Đúng", "correct": False, "misconception": "Nhầm kiến thức nền"},
                {"label": "Sai", "correct": True, "misconception": None},
            ]
            conn.execute(
                "update items set payload=%s where payload->>'id'=%s", (Jsonb(payload), item)
            )
        assert client.post("/attempts", json=body).json() == results[0].json()
        with psycopg.connect(database_url) as conn:
            payload["status"] = "needs_review"
            conn.execute(
                "update items set payload=%s where payload->>'id'=%s", (Jsonb(payload), item)
            )
        assert client.post("/attempts", json=body).json() == results[0].json()
        assert client.post("/attempts", json=body | {"answer": 1}).status_code == 409
    with psycopg.connect(database_url) as conn:
        assert conn.execute(
            "select count(*) from attempts where learner_id=%s", (learner,)
        ).fetchone() == (1,)
        assert conn.execute(
            "select count(*) from attempt_replays where learner_id=%s", (learner,)
        ).fetchone() == (1,)


def test_wrong_placement_does_not_remediate(
    database_url: str, learning_data: tuple[str, str, str]
) -> None:
    learner, subject, item = learning_data
    with TestClient(
        create_app(
            Settings(
                database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None
            )
        )
    ) as client:
        assert (
            client.post(
                "/placement/next", json={"learner_id": learner, "subject": subject}
            ).status_code
            == 200
        )
        response = client.post(
            "/attempts", json={"learner_id": learner, "item_id": item, "answer": 1}
        )
        assert response.status_code == 200
        assert "remediation" not in response.json()
        assert [t["kind"] for t in response.json()["traces"]] == ["bkt_update"]
