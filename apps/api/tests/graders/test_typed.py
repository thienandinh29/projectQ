"""Typed-answer grading (specs/vocabulary). The baseline normaliser is tested here.

The owner extends both the normaliser and these tests.

Rule that must keep holding whatever is added: a misspelling is a wrong answer.
"""

import pytest

from app.graders.typed import grade_typed, normalise


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("decision", "decision"),
        ("  Decision  ", "decision"),  # case and surrounding space
        ("take   advantage", "take advantage"),  # inner whitespace collapsed
        ("TAKE\tadvantage\n", "take advantage"),
        ("café", "café"),
        ("café", "café"),  # NFC: a decomposed é equals a composed é
    ],
)
def test_normalise_baseline(typed: str, expected: str) -> None:
    assert normalise(typed) == expected


def test_a_correct_answer_passes_whatever_the_case_or_spacing() -> None:
    assert grade_typed("  MAKE ", ["make"])
    assert grade_typed("make", ["Make"])


def test_a_misspelling_is_wrong() -> None:
    assert not grade_typed("desicion", ["decision"])
    assert not grade_typed("decison", ["decision"])
    assert not grade_typed("decisions", ["decision"])  # a different form is a different answer


def test_authored_variants_are_accepted_and_nothing_else_is() -> None:
    accepted = ["colour", "color"]
    assert grade_typed("Color", accepted)
    assert not grade_typed("colr", accepted)


def test_an_empty_answer_is_wrong() -> None:
    assert not grade_typed("", ["decision"])
    assert not grade_typed("   ", ["decision"])
    assert not grade_typed("x", [])
