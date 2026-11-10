import pytest
from pydantic import ValidationError

from app.graders.mcq import Item, Option, grade, learner_item


def item() -> Item:
    return Item(
        id="q1",
        prompt_vi="Oxy đến từ đâu?",
        difficulty=0.4,
        source="https://example.org",
        chunk_ids=["chunk-1"],
        status="verified",
        options=[
            Option(label="Nước", correct=True),
            Option(label="CO2", correct=False, misconception="oxygen-from-co2"),
        ],
    )


def test_grade_is_deterministic_and_maps_misconception() -> None:
    assert grade(item(), 0).correct
    assert grade(item(), 0).misconception is None
    assert grade(item(), 1).misconception == "oxygen-from-co2"


def test_learner_response_contains_no_answer_key_or_misconception() -> None:
    response = learner_item(item()).model_dump()
    assert response == {
        "id": "q1",
        "kind": "mcq",
        "prompt_vi": "Oxy đến từ đâu?",
        "options": [{"label": "Nước"}, {"label": "CO2"}],
    }


@pytest.mark.parametrize("index", [-1, 2, True])
def test_invalid_answer(index: int) -> None:
    with pytest.raises(ValueError):
        grade(item(), index)


def test_unverified_item_not_served_or_graded() -> None:
    pending = item().model_copy(update={"status": "needs_review"})
    with pytest.raises(ValueError, match="Unverified"):
        learner_item(pending)
    with pytest.raises(ValueError, match="Unverified"):
        grade(pending, 0)


def test_invalid_key_or_missing_misconception_rejected() -> None:
    data = item().model_dump()
    data["options"][1]["correct"] = True
    with pytest.raises(ValidationError):
        Item.model_validate(data)
    data = item().model_dump()
    del data["options"][1]["misconception"]
    with pytest.raises(ValidationError):
        Item.model_validate(data)
