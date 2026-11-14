"""Grammar analysis on recorded LanguageTool 6.8 responses (specs/writing/step-2.2.md)."""

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from app.curriculum.course import load_course
from app.engine import bkt
from app.writing.error_map import Edit, ErrorMap, load_error_map
from app.writing.grammar import (
    Issue,
    analyse_grammar,
    apply_matches,
    choose_evidence,
    edit_distance,
    is_minimal,
)
from app.writing.languagetool import Match, kept_matches, parse_matches

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "lt-6.8.json").read_text("utf-8"))
MAP = load_error_map(ROOT / "data" / "writing" / "error-map.yaml")


@cache
def nlp_and_annotator() -> tuple[Any, Any]:
    import errant
    import spacy

    nlp = spacy.load("en_core_web_sm")
    return nlp, errant.load("en", nlp)


def matches_for(name: str) -> tuple[str, list[Match]]:
    f = FIXTURES[name]
    return f["text"], kept_matches(parse_matches(f["en-GB"]), parse_matches(f["en-US"]))


def run(name: str) -> list[Issue]:
    text, matches = matches_for(name)
    nlp, annotator = nlp_and_annotator()
    return list(analyse_grammar(text, matches, nlp, annotator, MAP).issues)


def m(offset: int, length: int, *reps: str, category: str = "GRAMMAR", rule: str = "R") -> Match:
    return Match(offset, length, rule, category, "msg", reps)


def test_the_recorded_sample_is_typed_and_mapped() -> None:
    got = [(i.text, i.errant_type, i.node) for i in run("sample")]
    assert got == [
        ("go", "R:VERB:SVA", "present-simple"),
        ("is", "R:VERB:SVA", "be-present"),
        (
            "a apples",
            "R:NOUN:NUM",
            "plural-nouns",
        ),  # LanguageTool's choice; the owner's check decides
        ("more bigger", "U:ADV", "comparatives"),
        ("visit", "R:VERB:FORM", None),  # no node for verb forms yet
        ("last year", None, None),  # a match without a suggestion: shown, untyped
        ("Their", "R:SPELL", None),
        ("many reason", "R:NOUN:NUM", "plural-nouns"),
    ]
    assert all(i.explain_vi for i in run("sample") if i.errant_type)


def test_a_clean_essay_has_no_issues_and_british_or_american_spelling_both_pass() -> None:
    assert run("clean") == []
    text, matches = matches_for("sample")
    assert "colour" in text and not any(text[x.offset : x.end] == "colour" for x in matches)


def test_categories_and_the_two_variant_spelling_rule() -> None:
    spell = Match(0, 5, "MORFOLOGIK_RULE_EN_GB", "TYPOS", "", ("x",))
    us_spell = Match(0, 5, "MORFOLOGIK_RULE_EN_US", "TYPOS", "", ("x",))
    style = m(10, 3, "y", category="STYLE")
    grammar = m(20, 2, "z")
    assert kept_matches([spell, style, grammar], [us_spell]) == [spell, grammar]
    assert kept_matches([spell, grammar], []) == [grammar]  # only one variant flags it


def test_matches_are_applied_left_to_right_without_overlaps() -> None:
    text = "She go to school ."
    corrected, applied = apply_matches(
        text, 0, len(text), [m(4, 2, "goes"), m(4, 5, "went to"), m(7, 2)]
    )
    assert corrected == "She goes to school ." and len(applied) == 1


def test_a_correction_that_changes_more_than_its_matches_is_discarded() -> None:
    text = "She go to school every day."
    rewrite = m(0, len(text) - 1, "Every day, the girl walks to her school by bus")
    corrected, applied = apply_matches(text, 0, len(text), [rewrite])
    assert is_minimal(text, "She goes to school every day.", text, [m(4, 2, "goes")])
    assert edit_distance(["a", "b", "c"], ["a", "c", "d"]) == 2
    nlp, annotator = nlp_and_annotator()
    # a match covering the whole sentence may rewrite it; a small match with a long
    # suggestion may not
    huge = m(4, 2, "goes, as all of the children in her class do on weekdays,")
    assert not is_minimal(text, apply_matches(text, 0, len(text), [huge])[0], text, [huge])
    issues = analyse_grammar(text, [huge], nlp, annotator, MAP).issues
    assert [(i.suggestion is not None, i.errant_type, i.node) for i in issues] == [
        (True, None, None)
    ]
    assert corrected and applied


@pytest.mark.parametrize(
    ("edit", "node"),
    [
        (Edit(type="M:DET"), "articles-basic"),
        (Edit(type="R:NOUN:NUM"), "plural-nouns"),
        (Edit(type="R:VERB:SVA", corrected_lemmas=("be",)), "be-present"),
        (Edit(type="R:VERB:SVA", corrected_lemmas=("go",)), "present-simple"),
        (Edit(type="R:ADJ:FORM", corrected_tags=("JJR",)), "comparatives"),
        (Edit(type="R:ADJ:FORM", corrected_tags=("JJS",)), "superlatives"),
        (Edit(type="R:ADJ:FORM", corrected_tags=("JJ",)), None),
        (Edit(type="U:ADV", original_lemmas=("more",)), "comparatives"),
        (Edit(type="U:ADV", original_lemmas=("most",)), "superlatives"),
        (Edit(type="U:ADV", original_lemmas=("very",)), None),
        (
            Edit(
                type="M:VERB:TENSE",
                corrected_lemmas=("have", "visit"),
                corrected_tags=("VBP", "VBN"),
            ),
            "present-perfect-form",
        ),
        (
            Edit(type="R:VERB:TENSE", original_lemmas=("have", "visit"), corrected_tags=("VBD",)),
            "present-perfect-vs-past",
        ),
        (Edit(type="R:VERB:TENSE", corrected_tags=("VBZ",)), None),
        (Edit(type="R:PREP"), None),
        (Edit(type="R:SPELL"), None),
        (Edit(type="R:NOT:IN:MAP"), None),
    ],
)
def test_every_row_of_the_error_map(edit: Edit, node: str | None) -> None:
    row = MAP.lookup(edit)
    assert (row.node if row else None) == node


def test_the_error_map_names_only_hidden_nodes_of_its_course() -> None:
    course = load_course(ROOT / "data" / "courses" / "english-ielts.yaml")
    assert MAP.problems(course) == []
    bad = MAP.model_copy(update={"rows": (*MAP.rows, MAP.rows[0].model_copy(
        update={"node": "nouns-articles"}))})  # fmt: skip
    assert bad.problems(course) == ["DET: 'nouns-articles' is not a hidden node of english-ielts"]
    with pytest.raises(ValueError):
        ErrorMap.model_validate({**MAP.model_dump(), "observation": {"slip": 0.6, "guess": 0.5}})


def test_evidence_is_capped_one_per_node_most_frequent_first() -> None:
    def issue(i: int, node: str | None, start: int) -> Issue:
        return Issue(i, "s", 0, start, start + 1, "x", "y", "GRAMMAR", "R", "m", "R:X", node, "e")

    issues = [issue(0, "b", 0), issue(1, "a", 5), issue(2, "a", 9), issue(3, None, 1),
              issue(4, "c", 3), issue(5, "d", 4)]  # fmt: skip
    assert [i.id for i in choose_evidence(issues, 3)] == [1, 0, 4]
    assert choose_evidence(issues, 0) == []
    assert choose_evidence([issue(0, None, 0)], 3) == []


def test_the_writing_observation_model_moves_mastery_gently() -> None:
    params = MAP.params()
    assert params.p_transit == 0  # an error is evidence, not practice
    once = bkt.update(0.95, False, params)
    twice = bkt.update(once, False, params)
    assert round(once, 2) == 0.90 and round(twice, 2) == 0.83
    assert bkt.update(0.95, False, bkt.DEFAULT_PARAMS["mcq"]) < once  # gentler than an MCQ
