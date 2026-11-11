"""Real SQL/API/engine case; model replies are fixtures, not live verification."""

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.content.repository import Repository
from app.db import create_pool
from app.engine import bkt
from app.guardrails.answerability import verify_item
from app.main import create_content_app
from tests.content.fakes import FakeGateway, topic


def test_session_to_practice_persists_engine_state(database_url: str) -> None:
    """The suite creates/drops a dedicated DB; the local UI DB stays untouched."""
    sources, chunks, graph, drafts = topic()
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        repo.save_material("python-conditions", sources, chunks)
        repo.save_graph("python-conditions", graph)
        checked = []
        for draft in drafts:
            fake = FakeGateway()
            fake.item = draft
            fake.chunks = [chunk for chunk in chunks if chunk.chunk_id in draft.chunk_ids]
            checked.append(asyncio.run(verify_item(draft, chunks, fake)))
        repo.save_items("python-conditions", checked)

        models = FakeGateway()
        settings = Settings(_env_file=None, database_url=database_url, api_key="p5-test-only")
        app = create_content_app(settings, repository=repo, gateway=models)
        with TestClient(app, headers={"X-API-Key": settings.api_key}) as client:
            created = client.post("/learners", json={"display_name": "P5 SQL engine case"})
            assert created.status_code == 200, created.text
            learner = created.json()["learner_id"]
            scope = {"learner_id": learner, "subject": "python-conditions"}
            assert client.post("/placement/next", json=scope).status_code == 409
            reviewed = client.get("/graph/review", params={"subject": scope["subject"]})
            assert reviewed.status_code == 200, reviewed.text
            snapshot = reviewed.json()
            assert snapshot["confirmed"] is False
            accepted = client.post(
                "/graph/confirm",
                json={key: snapshot[key] for key in ("subject", "graph_revision")},
            )
            assert accepted.status_code == 200, accepted.text

            observations = []

            def answer(
                public: dict[str, Any], *, correct: bool, replay: bool = False
            ) -> dict[str, Any]:
                assert set(public) == {"id", "kind", "prompt_vi", "options"}
                with repo.transaction() as conn:
                    bundle = repo.servable(conn, public["id"])
                    assert bundle is not None
                    prior_row = conn.execute(
                        "select m.p_known from mastery m join concepts c on c.id=m.concept_id "
                        "where m.learner_id=%s and c.slug=%s",
                        (learner, bundle.item.concept),
                    ).fetchone()
                prior = prior_row[0] if prior_row else 0.2
                choice = next(
                    i for i, option in enumerate(bundle.item.options) if option.correct == correct
                )
                body = {
                    "learner_id": learner,
                    "item_id": public["id"],
                    "answer": choice,
                    "hints_used": 0,
                    "client_attempt_id": str(uuid4()),
                }
                response = client.post("/attempts", json=body)
                assert response.status_code == 200, response.text
                result: dict[str, Any] = response.json()
                assert result["correct"] is correct
                expected = bkt.update(prior, correct, bkt.DEFAULT_PARAMS["mcq"])
                assert result["p_known"] == pytest.approx(expected)
                with repo.transaction() as conn:
                    stored = conn.execute(
                        "select m.p_known from mastery m join concepts c on c.id=m.concept_id "
                        "where m.learner_id=%s and c.slug=%s",
                        (learner, bundle.item.concept),
                    ).fetchone()
                    assert stored and stored[0] == pytest.approx(expected)
                    before = conn.execute("select count(*) from attempts").fetchone()
                if replay:
                    again = client.post("/attempts", json=body)
                    assert again.status_code == 200 and again.json() == result
                    with repo.transaction() as conn:
                        assert conn.execute("select count(*) from attempts").fetchone() == before
                observations.append(
                    {
                        "concept": bundle.item.concept,
                        "correct": correct,
                        "prior": prior,
                        "posterior": result["p_known"],
                    }
                )
                return result

            placement_answers = 0
            for _ in range(11):  # the Bayesian placer asks at most 10 questions
                step = client.post("/placement/next", json=scope)
                assert step.status_code == 200, step.text
                selection = step.json()
                if selection["done"]:
                    break
                answer(selection["item"], correct=placement_answers > 0)
                placement_answers += 1
            else:
                pytest.fail("placement did not finish within its question budget")

            practice = client.get("/next-item", params=scope)
            assert practice.status_code == 200, practice.text
            wrong = answer(practice.json()["item"], correct=False, replay=True)
            assert any(trace["kind"] == "root_cause" for trace in wrong["traces"])
            practice = client.get("/next-item", params=scope)
            assert practice.status_code == 200, practice.text
            answer(practice.json()["item"], correct=True)

            with repo.transaction() as conn:
                counts = {
                    table: conn.execute(
                        f"select count(*) from {table} where learner_id=%s", (learner,)
                    ).fetchone()[0]  # type: ignore[index]
                    for table in (
                        "attempts",
                        "mastery",
                        "decision_traces",
                        "review_cards",
                        "learner_graph_confirmations",
                    )
                }
                session = conn.execute(
                    "select placement_complete,phase,pending_item from p4_learning_sessions "
                    "where learner_id=%s",
                    (learner,),
                ).fetchone()
                cards = conn.execute(
                    "select due_at,fsrs_state from review_cards where learner_id=%s",
                    (learner,),
                ).fetchall()
            assert counts["attempts"] == placement_answers + 2
            assert counts["mastery"] == len(graph.concepts)
            assert counts["decision_traces"] >= counts["attempts"]
            assert counts["learner_graph_confirmations"] == 1
            assert cards and all(due and state for due, state in cards)
            assert session == (True, "practice", None)
            assert client.get("/reviews/due", params={"learner_id": learner}).status_code == 200
            assert models.calls == []
            print(
                json.dumps(
                    {
                        "case": "wrong placement, wrong practice, correct practice, retry",
                        "real_database_api_engine": True,
                        "model_replies": "test fixtures",
                        "live_model_calls": 0,
                        "placement_answers": placement_answers,
                        "db_counts": counts,
                        "observations": observations,
                    }
                )
            )
