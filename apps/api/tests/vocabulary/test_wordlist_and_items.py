"""Word lists and the items built from them (specs/vocabulary)."""

from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.vocabulary.items import (
    KINDS,
    build_item,
    count_for,
    grade,
    item_id,
    kinds_for,
    learner_view,
    parse_item_id,
    pick,
)
from app.vocabulary.wordlist import WordList, load_wordlist, occurrences

SEED = Path(__file__).resolve().parents[4] / "data" / "vocabulary" / "core-seed.yaml"
WL = load_wordlist(SEED)


def word(lemma: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "lemma": lemma, "pos": "noun", "level": "B1", "definition": "a thing that is described",
        "examples": [{"text": f"I saw the {lemma} today.", "answer": lemma}],
    }  # fmt: skip
    return {**base, **over}


def wordlist(*words: dict[str, Any]) -> dict[str, Any]:
    return {"slug": "t", "title_vi": "T", "title_en": "T", "status": "draft", "words": list(words)}


FOUR = [word(w) for w in ("apple", "bridge", "candle", "doctor")]


def test_the_seed_list_loads_and_every_word_yields_items() -> None:
    assert len(WL.words) >= 24 and WL.status == "draft"
    levels = {w.level for w in WL.words}
    assert {"A2", "B1", "B2", "C1"} <= levels
    total = 0
    for w in WL.words:
        for kind in kinds_for(w):
            for n in range(count_for(w, kind)):
                item = build_item(WL, w, kind, n)
                assert item.accepted and item.accepted[0]
                total += 1
    assert total >= 60


def test_whole_word_matching_ignores_case_and_longer_words() -> None:
    assert occurrences("make", "Make a decision") == 1
    assert occurrences("make", "to remake it") == 0
    assert occurrences("act", "the actor will act") == 1


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"examples": [{"text": "A sentence without it.", "answer": "apple"}]}, "exactly once"),
        (
            {"examples": [{"text": "An apple and another apple.", "answer": "apple"}]},
            "exactly once",
        ),
        ({"definition": "a round apple you eat"}, "definition contains the word"),
        ({"collocations": [{"phrase": "take a risk", "blank": "make"}]}, "exactly once"),
        ({"forms": [{"base": "x", "sentence": "no blank here", "answer": "y"}]}, "exactly one ___"),
        ({"forms": [{"base": "x", "sentence": "___ and ___", "answer": "y"}]}, "exactly one ___"),
        ({"level": "D9"}, "level"),
        ({"examples": []}, "at least 1"),
    ],
)
def test_a_broken_word_is_refused(change: dict[str, Any], why: str) -> None:
    with pytest.raises(ValidationError, match=why):
        WordList.model_validate(wordlist(word("apple", **change), *FOUR[1:]))


def test_duplicate_words_and_tiny_lists_are_refused() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        WordList.model_validate(wordlist(*FOUR, word("apple")))
    with pytest.raises(ValidationError, match="at least 4"):
        WordList.model_validate(wordlist(*FOUR[:3]))
    assert WordList.model_validate(
        wordlist(*FOUR, word("apple", pos="verb"))
    )  # same lemma, other pos


def test_the_same_id_always_gives_the_same_item() -> None:
    w = WL.get("decision:noun")
    assert w is not None
    first = build_item(WL, w, "meaning", 0)
    for _ in range(5):
        assert build_item(WL, w, "meaning", 0) == first
    assert first.options is not None
    assert len(set(first.options)) == 4 and "decision" in first.options


def test_distractors_prefer_the_same_part_of_speech_and_the_nearest_level() -> None:
    w = WL.get("inevitable:adjective")
    assert w is not None
    item = build_item(WL, w, "meaning", 0)
    assert item.options is not None
    wrong = [o for o in item.options if o != "inevitable"]
    assert len(wrong) == 3 and all(
        WL.get(f"{o}:adjective") for o in wrong
    )  # only 5 adjectives exist


def test_the_learner_view_never_contains_the_key() -> None:
    for w in WL.words:
        for kind in kinds_for(w):
            item = build_item(WL, w, kind, 0)
            view = learner_view(item).model_dump_json()
            if kind != "meaning":
                assert item.accepted[0] not in learner_view(item).prompt.split()
            assert "accepted" not in view and "word_key" not in view


def test_typed_items_blank_the_answer_and_give_the_first_letter() -> None:
    w = WL.get("decision:noun")
    assert w is not None
    gap = build_item(WL, w, "gapfill", 0)
    assert "___" in gap.prompt and "decision" not in gap.prompt and gap.hint == "d"
    col = build_item(WL, w, "collocation", 0)
    assert col.prompt == "___ a decision" and col.hint == "m" and col.accepted == ("make",)
    form = build_item(WL, w, "wordform", 0)
    assert "decide" in form.instruction_vi and form.accepted == ("decision",)


def test_grading_multiple_choice_and_typed() -> None:
    w = WL.get("decision:noun")
    assert w is not None
    meaning = build_item(WL, w, "meaning", 0)
    assert grade(meaning, "decision") and grade(meaning, " Decision ")
    assert not grade(meaning, "benefit")
    gap = build_item(WL, w, "gapfill", 0)
    assert grade(gap, "decision") and not grade(gap, "desicion") and not grade(gap, "")


def test_item_ids_round_trip_and_bad_ids_are_refused() -> None:
    iid = item_id("core-seed", "decision:noun", "gapfill", 0)
    assert parse_item_id(iid) == ("core-seed", "decision:noun", "gapfill", 0)
    for bad in [
        "",
        "a|b|c",
        "core-seed|decision:noun|nonsense|0",
        "x|y|meaning|-1",
        "x|y|meaning|a",
    ]:
        with pytest.raises(ValueError):
            parse_item_id(bad)
    w = WL.get("decision:noun")
    assert w is not None
    for kind, n in [("meaning", 1), ("gapfill", 5), ("wordform", 3)]:
        with pytest.raises(ValueError):
            build_item(WL, w, kind, n)  # type: ignore[arg-type]
    plain = WL.get("increase:verb")
    assert plain is not None and "collocation" not in kinds_for(plain)
    with pytest.raises(ValueError):
        build_item(WL, plain, "collocation", 0)


def test_kinds_rotate_with_the_number_of_reviews() -> None:
    w = WL.get("decision:noun")
    assert w is not None
    seen = [pick(w, r)[0] for r in range(len(kinds_for(w)) * 2)]
    assert seen[:4] == ["meaning", "gapfill", "collocation", "wordform"] == seen[4:]
    assert pick(w, 0) == ("meaning", 0)  # a new word is asked its meaning first
    assert set(KINDS) >= set(seen)


def test_the_yaml_round_trips_through_the_models() -> None:
    raw = yaml.safe_load(SEED.read_text(encoding="utf-8"))
    assert WordList.model_validate(raw) == WL
