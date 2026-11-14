"""LLM feedback and corrections, checked by code (specs/writing/step-2.4.md); no model needed."""

from functools import cache
from typing import Any

import pytest

from app.writing.error_map import load_error_map
from app.writing.feedback import FeedbackOut, disagreement, overall_band, verify
from app.writing.llm_corrections import CorrectionsOut, Sentence, corrections, unflagged
from tests.writing.test_grammar import MAP, nlp_and_annotator

ESSAY = (
    "Many people believe that public transport is the answer to traffic. "
    "In my opinion, the government should invest in buses and metro lines."
)


def criterion(*points: dict[str, Any], band: float = 6.0) -> dict[str, Any]:
    return {"band": band, "points": list(points)}


def point(*quotes: str, kind: str = "strength") -> dict[str, Any]:
    return {"kind": kind, "point_vi": "Bạn nêu quan điểm rõ ràng.", "quotes": list(quotes)}


def out(**overrides: dict[str, Any]) -> FeedbackOut:
    base = {c: criterion(point("the government should invest")) for c in ("tr", "cc", "lr", "gra")}
    return FeedbackOut.model_validate(base | overrides)


def test_quotes_must_be_in_the_essay_and_points_without_one_are_dropped() -> None:
    fb = verify(ESSAY, out(
        tr=criterion(
            point("public  transport is\nthe answer"),  # whitespace differs: still the essay's
            point("cars are terrible for cities", kind="issue"),  # not in the essay: dropped
        ),
        lr=criterion(point("In my opinion, the", "invest in")),  # second quote too short
    ))  # fmt: skip
    assert [p.quotes for p in fb.criteria["tr"]] == [("public transport is the answer",)]
    assert fb.criteria["lr"][0].quotes == ("In my opinion, the",)
    assert fb.dropped == 1 and (fb.quotes_checked, fb.quotes_kept) == (6, 4)
    curly = "Many people believe that public transport is the answer to traffic\u2019s growth."
    kept = verify(curly, out(tr=criterion(point("the answer to traffic's growth"))))
    assert kept.criteria["tr"][0].quotes == ("the answer to traffic's growth",)


def test_the_model_band_is_kept_out_of_the_shown_feedback() -> None:
    shown = verify(ESSAY, out()).to_json("deepseek-x")
    assert "band" not in str(shown) and shown["model"] == "deepseek-x"


@pytest.mark.parametrize(
    ("bands", "overall"),
    [
        ((6, 6, 6, 6.5), 6.0),
        ((6, 6, 6.5, 6.5), 6.5),
        ((6, 6.5, 6.5, 6.5), 6.5),
        ((6, 7, 7, 7), 7.0),
    ],
)
def test_overall_rounds_like_ielts(bands: tuple[float, ...], overall: float) -> None:
    # means 6.125 -> 6.0, 6.25 -> 6.5, 6.375 -> 6.5, 6.75 -> 7.0
    assert overall_band(bands) == overall


def test_disagreement_of_more_than_a_band_makes_the_range_uncertain() -> None:
    assert disagreement(5.5, 6.5, 7.0) is None  # middle 6.0: 1.0 apart is allowed
    assert disagreement(5.5, 6.5, 7.5) and "1 band" in str(disagreement(5.5, 6.5, 7.5))
    assert disagreement(5.5, 6.5, 4.5)


@cache
def annotator() -> Any:
    return nlp_and_annotator()[1]


def test_minimal_corrections_are_typed_and_rewrites_discarded() -> None:
    sents = [Sentence(0, "She go to school every day."), Sentence(30, "I like dogs.")]
    fixes = CorrectionsOut.model_validate({"fixes": [
        {"index": 0, "corrected": "She goes to school every day."},
        {"index": 1, "corrected": "Personally, I am extremely fond of all kinds of dogs."},
        {"index": 1, "corrected": "I like dogs."},  # a second answer for the same sentence: ignored
        {"index": 9, "corrected": "Out of range."},
    ]})  # fmt: skip
    issues, discarded = corrections(sents, fixes, annotator(), MAP, first_id=5)
    assert discarded == 1
    assert [(i.id, i.text, i.suggestion, i.errant_type, i.node, i.source, i.evidence)
            for i in issues] == [
        (5, "go", "goes", "R:VERB:SVA", "present-simple", "llm", False)
    ]  # fmt: skip
    assert issues[0].start == 4 and issues[0].sentence_start == 0


def test_only_sentences_the_tools_did_not_flag_are_sent() -> None:
    from app.writing.grammar import Issue

    flagged = [Issue(0, "s", 30, 31, 33, "x", "y", "GRAMMAR", "R", "m", None, None, None)]
    sents = [Sentence(0, "a b c."), Sentence(30, "d e f."), Sentence(60, "g h i.")]
    assert [s.start for s in unflagged(sents, flagged)] == [0, 60]


def test_the_shipped_error_map_is_used() -> None:
    assert load_error_map is not None and MAP.status in ("draft", "reviewed")
