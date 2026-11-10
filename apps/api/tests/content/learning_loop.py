"""Offline scenario driver for tests, NOT another backend or a verified demo."""

import asyncio
import json
from datetime import datetime, timedelta

from app.content.integration import contract_graph, contract_item
from app.content.learning import (
    attempt_review,
    graph_confirmed,
    graph_revision,
    missing_material,
    submitted_feedback,
)
from app.engine import bkt, path, placement, remediation
from app.engine.graph import Graph as EngineGraph
from app.graders.mcq import Item as GraderItem
from app.graders.mcq import grade
from app.guardrails.answerability import is_currently_verified, verify_item
from app.tutor.hints import hint
from tests.content.fakes import ROOT, FakeGateway, topic


async def replay() -> dict[str, object]:
    fixture = json.loads(
        (ROOT / "data/golden/python-conditions/learning-loop.fixture.json").read_text(
            encoding="utf-8"
        )
    )
    sources, chunks, graph, items = topic()
    assert all(item.status == "needs_review" for item in items)
    now = datetime.fromisoformat(fixture["at"])
    approved: set[tuple[str, str, str]] = set()

    def confirmation(learner: str, subject: str, revision: str) -> bool:
        return (learner, subject, revision) in approved

    learner, subject = "fixture-learner", fixture["subject"]
    assert not graph_confirmed(confirmation, learner, subject, graph)
    # Both entry routes converge on this same proposed map; no separate learning engine.
    for entry in fixture["entries"]:
        assert not entry["search_performed"]
    assert missing_material(graph, chunks, {c.chunk_id for c in chunks})
    approved.add((learner, subject, graph_revision(graph)))
    assert graph_confirmed(confirmation, learner, subject, graph)

    engine = EngineGraph.from_contract(contract_graph(graph))
    answers: list[placement.Answer] = []
    while True:
        slug, placement_trace = placement.next_question(engine, answers, now=now)
        if slug is None:
            break
        # Explicit simulated observations: foundations right; downstream concepts wrong.
        answers.append(placement.Answer(slug, not bool(engine.parents[slug])))
        assert len(answers) <= placement.MAX_QUESTIONS
    mastery = placement.seed_mastery(engine, answers)
    assert all(p < bkt.MASTERY_THRESHOLD for p in mastery.values())
    step, next_trace = path.next_step(engine, mastery, now=now)
    assert step.concept_slug and next_trace.rule_vi
    draft = next(item for item in items if item.concept == step.concept_slug)
    fake = FakeGateway()
    fake.item = draft
    concept = next(c for c in graph.concepts if c.slug == draft.concept)
    fake.chunks = [c for c in chunks if c.chunk_id in concept.chunk_ids]
    checked = await verify_item(draft, chunks, fake)
    # Test-only trust simulation remains confined to memory.
    assert is_currently_verified(checked, chunks)
    selected = next(option for option in checked.options if not option.correct)
    assert submitted_feedback(checked, chunks, sources, selected.id, submitted=False) is None
    suggestion = await hint(
        checked,
        1,
        selected.label,
        chunks,
        "free",
        sources=sources,
        gateway=fake,
    )
    assert suggestion and suggestion.citations
    fake.overrides = {"no_answer_leak": False}
    withheld = await hint(checked, 2, selected.label, chunks, "free", sources=sources, gateway=fake)
    assert withheld is None

    index = checked.options.index(selected)
    result = grade(GraderItem.model_validate(contract_item(checked).model_dump()), index)
    assert not result.correct
    feedback = submitted_feedback(checked, chunks, sources, selected.id, submitted=True)
    assert feedback and feedback.citations and feedback.misconception_signal_vi
    assert fixture["personal_note_vi"] not in feedback.explanation_vi
    prior = mastery[checked.concept]
    posterior, update_trace = bkt.update_traced(
        prior,
        False,
        bkt.DEFAULT_PARAMS["mcq"],
        concept_slug=checked.concept,
        now=now,
        item_id=checked.id,
        misconception=result.misconception,
    )
    mastery[checked.concept] = posterior
    plan, remediation_trace = remediation.remediate(
        engine,
        mastery,
        checked.concept,
        now=now,
        item_id=checked.id,
        misconception=result.misconception,
    )
    assert plan.target_slug in set(engine.ancestors(checked.concept)) | {checked.concept}
    scheduled = attempt_review(
        None,
        False,
        bkt.is_mastered(posterior),
        now,
        concept=checked.concept,
        item_id=checked.id,
        hints_used=1,
    )
    assert scheduled is not None
    review, review_trace = scheduled
    assert review_trace.rule == "review.again"
    before_wait = dict(mastery)
    today, today_trace = path.next_step(
        engine,
        mastery,
        now=review.due_at + timedelta(hours=2),
        due_reviews={checked.concept: review.due_at},
    )
    assert today.kind == "review" and mastery == before_wait
    return {
        "mode": fixture["mode"],
        "label_vi": fixture["label_vi"],
        "source_selection": "explicit sample; no search",
        "goal_vi": fixture["goal_vi"],
        "exam_date": (now + timedelta(days=fixture["exam_in_days"])).date().isoformat(),
        "graph_confirmation": "in-memory callback, no HTTP persistence",
        "placement_answers": len(answers),
        "placement_rule": placement_trace.rule,
        "next_rule": next_trace.rule,
        "hint": "fake gateway, accepted and rejected cases",
        "feedback": "post-submission helper only, no HTTP endpoint",
        "mastery": {"prior": prior, "posterior": posterior, "rule": update_trace.rule},
        "remediation_rule": remediation_trace.rule,
        "review_rule": review_trace.rule,
        "today_rule": today_trace.rule,
        "exam_prioritization": "not implemented",
        "review_card_fixture": {
            "mode": "simulation",
            "origin": "wrong_answer",
            "concept": checked.concept,
            "question_vi": checked.prompt_vi,
            "answer_vi": feedback.correct_answer_vi,
            "explanation_vi": feedback.explanation_vi,
            "due_at": review.due_at.isoformat(),
            "chunk_ids": [str(c.chunk_id) for c in feedback.citations],
        },
        "flashcards_with_question_answer": (
            "fixture only; no persistent flashcards or notes service"
        ),
        "real_verified_count": 0,
        "database_used": False,
        "pending_policy": fixture["pending_policy"],
        "steps": fixture["expected_steps"],
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(replay()), ensure_ascii=True, indent=2))
