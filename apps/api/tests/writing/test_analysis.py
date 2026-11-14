"""What plain code measures in an essay (specs/writing/step-2.1.md)."""

from pathlib import Path

import pytest

from app.writing.analysis import (
    analyse,
    linking_found,
    load_linking_words,
    paragraphs,
    sentences,
    words,
)
from app.writing.prompts import load_prompts

DATA = Path(__file__).resolve().parents[4] / "data" / "writing"
LINKING = load_linking_words(DATA / "linking-words.yaml")


@pytest.mark.parametrize(
    ("text", "n"),
    [
        ("I don't think so.", 4),
        ("I don\u2019t think so.", 4),  # a curly apostrophe typed on a phone
        ("A well-known fact.", 3),
        ("In 2025, 30% rose.", 4),
        ("— ... !", 0),
    ],
)
def test_counting_words(text: str, n: int) -> None:
    assert len(words(text)) == n


def test_sentences_and_paragraphs() -> None:
    text = "First point. Second point!\n\nIs it true? \n   \nYes"
    assert sentences(text) == ["First point.", "Second point!", "Is it true?", "Yes"]
    assert len(paragraphs(text)) == 3
    assert paragraphs("") == [] and sentences("") == []


def test_linking_words_are_whole_words_or_phrases() -> None:
    text = (
        "However, this is true. On the other hand, however small, thus... Howevering is not a word."
    )
    found = linking_found(text, LINKING)
    assert found["contrast"] == {"however": 2, "on the other hand": 1}
    assert found["cause_effect"] == {"thus": 1}
    assert "addition" not in found


def test_a_short_essay_is_flagged_and_a_long_one_is_not() -> None:
    short = analyse("Cities are busy. However, buses help.", 2, LINKING)
    assert short.words == 6 and short.sentences == 2 and not short.long_enough
    assert short.min_words == 250 and short.linking_groups_used == 1
    long_text = "\n\n".join(["This is a sentence with eight words in it."] * 32)
    long = analyse(long_text, 2, LINKING)
    assert long.words == 288 and long.long_enough and long.paragraphs == 32
    assert long.avg_sentence_words == 9.0 and long.longest_sentence_words == 9
    assert analyse("Words here.", 1, LINKING).min_words == 150


def test_the_prompts_and_linking_files_load() -> None:
    bank = load_prompts(DATA / "prompts.yaml")
    assert len(bank.prompts) >= 5 and all(p.task == 2 for p in bank.prompts)
    assert {"contrast", "addition", "conclusion"} <= set(LINKING)
