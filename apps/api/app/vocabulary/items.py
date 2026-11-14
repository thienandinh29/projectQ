"""Vocabulary items built from a word, deterministically (specs/vocabulary).

An item id is `<list>|<lemma>:<pos>|<kind>|<n>`. The server rebuilds the item from the id alone,
so no session state is kept and the answer key never reaches the client. Distractors come from a
generator seeded by the id, so the same id always gives the same options in the same order.
"""

import hashlib
import random
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.graders.typed import grade_typed, normalise
from app.vocabulary.wordlist import Word, WordList, blank_out

Kind = Literal["meaning", "gapfill", "collocation", "wordform"]
KINDS: tuple[Kind, ...] = ("meaning", "gapfill", "collocation", "wordform")
DISTRACTORS = 3


@dataclass(frozen=True)
class Item:
    """The full item, including the key. Never sent to a learner: use `learner_view`."""

    id: str
    kind: Kind
    word_key: str
    prompt: str
    instruction_vi: str
    options: tuple[str, ...] | None  # multiple choice (meaning); None for typed kinds
    hint: str | None  # first letter of the answer, for typed kinds
    accepted: tuple[str, ...]  # the correct answer first, then authored variants


class LearnerItem(BaseModel):
    id: str
    kind: Kind
    instruction_vi: str
    prompt: str
    options: list[str] | None
    hint: str | None


class WordCard(BaseModel):
    """What a learner sees about a word: before the first question (new words) and as feedback."""

    key: str
    lemma: str
    pos: str
    level: str
    definition: str
    vi: str | None
    example: str


def item_id(list_slug: str, word_key: str, kind: Kind, n: int) -> str:
    return f"{list_slug}|{word_key}|{kind}|{n}"


def parse_item_id(value: str) -> tuple[str, str, Kind, int]:
    parts = value.split("|")
    if len(parts) != 4 or parts[2] not in KINDS or not parts[3].isdecimal() or len(value) > 200:
        raise ValueError("malformed item id")
    kind: Kind = parts[2]  # checked against KINDS just above
    return parts[0], parts[1], kind, int(parts[3])


def kinds_for(word: Word) -> list[Kind]:
    """The kinds this word has material for; `meaning` always works."""
    kinds: list[Kind] = ["meaning", "gapfill"]
    if word.collocations:
        kinds.append("collocation")
    if word.forms:
        kinds.append("wordform")
    return kinds


def count_for(word: Word, kind: Kind) -> int:
    """How many different items of this kind the word has."""
    return {
        "meaning": 1,
        "gapfill": len(word.examples),
        "collocation": len(word.collocations),
        "wordform": len(word.forms),
    }[kind]


def pick(word: Word, reviews: int) -> tuple[Kind, int]:
    """Which item to ask for a word reviewed `reviews` times: kinds rotate, then examples rotate."""
    kinds = kinds_for(word)
    kind = kinds[reviews % len(kinds)]
    return kind, (reviews // len(kinds)) % count_for(word, kind)


def _rng(value: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big"))


def _distractors(wordlist: WordList, word: Word, rng: random.Random) -> list[str]:
    """Three other words, preferring the same part of speech and the nearest level."""
    others = [w for w in wordlist.words if w.lemma != word.lemma]
    rng.shuffle(others)  # random order within equal keys, fixed by the id
    others.sort(
        key=lambda w: (w.pos != word.pos, abs(wordlist.level_index(w) - wordlist.level_index(word)))
    )
    return [w.lemma for w in others[:DISTRACTORS]]


def build_item(wordlist: WordList, word: Word, kind: Kind, n: int) -> Item:
    if kind not in kinds_for(word) or not 0 <= n < count_for(word, kind):
        raise ValueError("this word has no such item")
    iid = item_id(wordlist.slug, word.key, kind, n)
    if kind == "meaning":
        rng = _rng(iid)
        options = [word.lemma, *_distractors(wordlist, word, rng)]
        rng.shuffle(options)
        return Item(iid, kind, word.key, word.definition, "Chọn từ có nghĩa sau:",
                    tuple(options), None, (word.lemma,))  # fmt: skip
    if kind == "gapfill":
        ex = word.examples[n]
        return Item(iid, kind, word.key, blank_out(ex.answer, ex.text),
                    "Điền từ còn thiếu vào câu:", None, ex.answer[0].lower(),
                    (ex.answer, *ex.accepted))  # fmt: skip
    if kind == "collocation":
        col = word.collocations[n]
        return Item(iid, kind, word.key, blank_out(col.blank, col.phrase),
                    "Điền từ còn thiếu để tạo cụm từ:", None, col.blank[0].lower(),
                    (col.blank, *col.accepted))  # fmt: skip
    form = word.forms[n]
    return Item(iid, kind, word.key, form.sentence,
                f"Dùng dạng đúng của từ “{form.base}” để điền vào chỗ trống:", None,
                form.answer[0].lower(), (form.answer, *form.accepted))  # fmt: skip


def learner_view(item: Item) -> LearnerItem:
    return LearnerItem(
        id=item.id,
        kind=item.kind,
        instruction_vi=item.instruction_vi,
        prompt=item.prompt,
        options=list(item.options) if item.options else None,
        hint=item.hint,
    )


def grade(item: Item, answer: str) -> bool:
    if item.options is not None:  # multiple choice: the option text must match the key
        return normalise(answer) == normalise(item.accepted[0])
    return grade_typed(answer, item.accepted)


def card(word: Word) -> WordCard:
    return WordCard(
        key=word.key,
        lemma=word.lemma,
        pos=word.pos,
        level=word.level,
        definition=word.definition,
        vi=word.vi,
        example=word.examples[0].text,
    )
