"""P1 learning-flow replay with JSON storage; optional real P3 grading on ptest.

This tests algorithm/contract composition, not DB transactions or a live worker.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.engine import bkt, placement, srs
from app.engine.graph import Graph
from app.engine.path import next_step
from app.engine.remediation import remediate
from app.engine.trace import DecisionTrace
from app.schemas import Item, ItemSet

NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)


@pytest.mark.parametrize("use_p3_grader", [False, True])
def test_learning_flow_from_diagnostic_to_review(use_p3_grader: bool) -> None:
    p3 = pytest.importorskip("app.graders.mcq") if use_p3_grader else None
    graph = Graph.from_edges(["foundation", "target"], [("foundation", "target")])
    answers: list[placement.Answer] = []
    traces: list[DecisionTrace] = []
    while (slug := placement.next_question(graph, answers, now=NOW)[0]) is not None:
        answers.append(placement.Answer(slug, False, f"{slug}-diagnostic"))
    mastery = json.loads(json.dumps(placement.seed_mastery(graph, answers)))
    assert placement.gap(graph, answers) == "foundation"
    assert len(answers) <= placement.MAX_QUESTIONS
    assert next_step(graph, mastery, now=NOW)[0].concept_slug == "foundation"

    def item_for(slug: str) -> Item:
        values = ItemSet.model_validate(
            {
                "concept": slug,
                "misconceptions": [{"slug": "wrong", "description_vi": "Nhầm định nghĩa"}],
                "items": [
                    {
                        "id": f"{slug}-practice",
                        "prompt_vi": "Chọn phát biểu đúng?",
                        "difficulty": 0.4,
                        "source": "https://example.org/chapter",
                        "chunk_ids": ["chunk-1"],
                        "status": "verified",
                        "options": [
                            {"label": "Đúng", "correct": True},
                            {"label": "Sai", "correct": False, "misconception": "wrong"},
                        ],
                    }
                ],
            }
        )
        return values.items[0]

    def attempt(slug: str, index: int) -> bool:
        item = item_for(slug)
        if p3 is not None:
            grade = p3.grade(p3.Item.model_validate(item.model_dump()), index)
            correct = bool(grade.correct)
            misconception = grade.misconception
        else:
            correct = item.options[index].correct
            misconception = item.options[index].misconception
        mastery[slug], trace = bkt.update_traced(
            mastery[slug],
            correct,
            bkt.DEFAULT_PARAMS["mcq"],
            concept_slug=slug,
            now=NOW,
            item_id=item.id,
            misconception=misconception,
        )
        traces.append(trace)
        return correct

    # An incoming wrong target diagnostic must lead to the weaker foundation.
    assert not attempt("target", 1)
    plan, trace = remediate(graph, mastery, "target", now=NOW, misconception="wrong")
    traces.append(trace)
    assert plan.action == "review_prerequisite" and plan.target_slug == "foundation"
    assert plan.to_contract() is not None
    assert (
        next_step(graph, mastery, now=NOW, resume_origin=plan.origin_slug)[0].concept_slug
        == "foundation"
    )

    for _ in range(20):
        if bkt.is_mastered(mastery["foundation"]):
            break
        assert attempt("foundation", 0)
        mastery = json.loads(json.dumps(mastery))
    assert bkt.is_mastered(mastery["foundation"])
    step, trace = next_step(graph, mastery, now=NOW, resume_origin=plan.origin_slug)
    traces.append(trace)
    assert step.kind == "resume" and step.concept_slug == "target"

    for _ in range(20):
        if bkt.is_mastered(mastery["target"]):
            break
        assert attempt("target", 0)
    assert bkt.is_mastered(mastery["target"])
    assert next_step(graph, mastery, now=NOW)[0].kind == "done"

    stored = json.loads(json.dumps(srs.new_card(NOW).state))
    later = NOW + timedelta(hours=2)
    step, trace = next_step(graph, mastery, now=later, due_reviews={"foundation": NOW})
    traces.append(trace)
    assert step.kind == "review" and step.concept_slug == "foundation"
    reviewed, trace = srs.review_traced(stored, True, later, concept_slug="foundation")
    traces.append(trace)
    assert reviewed == srs.review(stored, True, later)
    assert reviewed.due_at > later
    assert (
        next_step(graph, mastery, now=later, due_reviews={"foundation": reviewed.due_at})[0].kind
        == "done"
    )
    assert [DecisionTrace.model_validate_json(t.model_dump_json()) for t in traces] == traces
