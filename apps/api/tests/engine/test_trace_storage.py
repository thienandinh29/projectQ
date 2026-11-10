"""Migration 0004: a DecisionTrace survives a round trip through `decision_traces`."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.engine.bkt import DEFAULT_PARAMS, update_traced
from app.engine.graph import Graph, root_cause
from app.engine.placement import Answer, next_question
from app.engine.srs import make_scheduler, new_card, review_traced
from app.engine.trace import Alternative, DecisionTrace

NOW = datetime(2026, 11, 7, 9, 30, tzinfo=UTC)
GRAPH = Graph.from_edges("abc", [("a", "b"), ("b", "c")], {"a": "A", "b": "B", "c": "C"})

INSERT = """
insert into decision_traces (learner_id, subject_id, concept_slug, attempt_id, kind, at, prior,
    posterior, evidence, rule, rule_vi, alternatives)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id
"""
SELECT = """
select kind, concept_slug, at, prior, posterior, evidence, rule, rule_vi, alternatives
from decision_traces where id = %s
"""


def _insert(
    conn: psycopg.Connection,
    learner: UUID,
    subject: UUID,
    t: DecisionTrace,
    attempt: UUID | None = None,
) -> UUID:
    data = t.model_dump(mode="json")
    row = conn.execute(
        INSERT,
        (
            learner,
            subject,
            t.concept_slug,
            attempt,
            t.kind,
            t.at,
            t.prior,
            t.posterior,
            Jsonb(data["evidence"]),
            t.rule,
            t.rule_vi,
            Jsonb(data["alternatives"]),
        ),
    ).fetchone()
    assert row is not None
    trace_id: UUID = row[0]
    return trace_id


def _load(conn: psycopg.Connection, trace_id: UUID) -> DecisionTrace:
    row = conn.execute(SELECT, (trace_id,)).fetchone()
    assert row is not None
    return DecisionTrace.model_validate(
        {
            "kind": row[0],
            "concept_slug": row[1],
            "at": row[2],
            "prior": row[3],
            "posterior": row[4],
            "evidence": row[5],
            "rule": row[6],
            "rule_vi": row[7],
            "alternatives": row[8],
        }
    )


@pytest.fixture
def db(database_url: str) -> Iterator[tuple[psycopg.Connection, UUID, UUID]]:
    with psycopg.connect(database_url) as conn:
        conn.execute("delete from learners")
        conn.execute("delete from subjects")
        learner = conn.execute(
            "insert into learners (display_name) values ('Minh') returning id"
        ).fetchone()
        subject = conn.execute(
            "insert into subjects (slug, name_vi, name_en) values ('py', 'Py', 'Py') returning id"
        ).fetchone()
        assert learner and subject
        yield conn, learner[0], subject[0]
        conn.rollback()


def _every_kind() -> list[DecisionTrace]:
    mcq = DEFAULT_PARAMS["mcq"]
    traces = [
        update_traced(0.5, False, mcq, concept_slug="c", now=NOW, item_id="i-1", misconception="m")[
            1
        ],
        root_cause(GRAPH, {"a": 0.9, "b": 0.3, "c": 0.2}, "c", now=NOW, item_id="i-1")[1],
        review_traced(
            new_card(NOW).state, True, NOW, concept_slug="c", scheduler=make_scheduler(fuzz=False)
        )[1],
        next_question(GRAPH, [], now=NOW)[1],
        next_question(GRAPH, [Answer("c", False), Answer("b", True)], now=NOW)[1],
        DecisionTrace(
            kind="next_item",
            concept_slug="b",
            at=NOW,
            rule="next_item.x",
            rule_vi="Câu tiếp theo về «B»",
            alternatives=[Alternative(concept_slug="a", p_known=0.9, why_not_vi="Đã vững")],
        ),
    ]
    assert {t.kind for t in traces} == {
        "bkt_update",
        "root_cause",
        "review",
        "placement_step",
        "next_item",
    }
    return traces


@pytest.mark.parametrize("trace", _every_kind(), ids=lambda t: f"{t.kind}-{t.rule}")
def test_every_kind_of_trace_round_trips_exactly(
    db: tuple[psycopg.Connection, UUID, UUID], trace: DecisionTrace
) -> None:
    conn, learner, subject = db
    assert _load(conn, _insert(conn, learner, subject, trace)) == trace


def test_vietnamese_text_is_stored_intact(db: tuple[psycopg.Connection, UUID, UUID]) -> None:
    conn, learner, subject = db
    trace = _every_kind()[1]
    stored = _load(conn, _insert(conn, learner, subject, trace))
    assert stored.rule_vi == trace.rule_vi and "«" in stored.rule_vi


def test_traces_belong_to_their_attempt_and_survive_its_deletion(
    db: tuple[psycopg.Connection, UUID, UUID],
) -> None:
    conn, learner, subject = db
    concept = conn.execute(
        "insert into concepts (subject_id, slug, name_vi, name_en) values (%s, 'c', 'C', 'C')"
        " returning id",
        (subject,),
    ).fetchone()
    assert concept
    item = conn.execute(
        "insert into items (concept_id, kind, prompt) values (%s, 'mcq', 'q') returning id",
        (concept[0],),
    ).fetchone()
    assert item
    attempt = conn.execute(
        "insert into attempts (learner_id, item_id, answer, is_correct)"
        " values (%s, %s, '0', false) returning id",
        (learner, item[0]),
    ).fetchone()
    assert attempt
    trace_id = _insert(conn, learner, subject, _every_kind()[0], attempt[0])
    rows = conn.execute(
        "select id from decision_traces where attempt_id = %s", (attempt[0],)
    ).fetchall()
    assert rows == [(trace_id,)]
    conn.execute("delete from attempts where id = %s", (attempt[0],))
    # History is kept; only the link is cleared.
    assert conn.execute(
        "select attempt_id from decision_traces where id = %s", (trace_id,)
    ).fetchone() == (None,)


def test_traces_are_deleted_with_their_learner(db: tuple[psycopg.Connection, UUID, UUID]) -> None:
    conn, learner, subject = db
    _insert(conn, learner, subject, _every_kind()[0])
    conn.execute("delete from learners where id = %s", (learner,))
    assert conn.execute("select count(*) from decision_traces").fetchone() == (0,)


@pytest.mark.parametrize(
    ("column", "value"),
    [("kind", "guess"), ("prior", 1.5), ("posterior", -0.1)],
)
def test_database_rejects_values_the_contract_forbids(
    db: tuple[psycopg.Connection, UUID, UUID], column: str, value: object
) -> None:
    conn, learner, subject = db
    good = _every_kind()[0]
    params = dict(kind=good.kind, prior=good.prior, posterior=good.posterior)
    params[column] = value  # type: ignore[assignment]
    with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
        conn.execute(
            "insert into decision_traces (learner_id, subject_id, concept_slug, kind, at, prior,"
            " posterior, rule, rule_vi) values (%s, %s, 'c', %s, %s, %s, %s, 'r', 'r')",
            (learner, subject, params["kind"], NOW, params["prior"], params["posterior"]),
        )


def test_evidence_must_be_an_object_and_alternatives_an_array(
    db: tuple[psycopg.Connection, UUID, UUID],
) -> None:
    conn, learner, subject = db
    for column, bad in (("evidence", "[]"), ("alternatives", "{}")):
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(
                "insert into decision_traces (learner_id, subject_id, concept_slug, kind, at,"
                f" rule, rule_vi, {column})"
                " values (%s, %s, 'c', 'review', %s, 'r', 'r', %s::jsonb)",
                (learner, subject, NOW, json.dumps(json.loads(bad))),
            )


def test_defaults_let_a_minimal_trace_through(db: tuple[psycopg.Connection, UUID, UUID]) -> None:
    conn, learner, subject = db
    row = conn.execute(
        "insert into decision_traces"
        " (learner_id, subject_id, concept_slug, kind, at, rule, rule_vi)"
        " values (%s, %s, 'c', 'review', %s, 'review.good', 'Ôn lại sau 3 ngày')"
        " returning evidence, alternatives, prior, posterior",
        (learner, subject, NOW),
    ).fetchone()
    assert row == ({}, [], None, None)
