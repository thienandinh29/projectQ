"""Vocabulary practice: a session of due and new words, and answers that schedule the next review.

Spec: specs/vocabulary. Items are rebuilt from their id (`vocabulary.items`), so the server keeps
no session state. FSRS decides when a word returns (`engine.srs`); there is no BKT and no
prerequisite graph for words.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.curriculum.course import LEVELS
from app.engine import srs
from app.engine.trace import DecisionTrace
from app.services.backend import learner_uuid, save_trace
from app.vocabulary import items as vitems
from app.vocabulary.wordlist import WordList, load_wordlist

DEFAULT_LIMIT = 20
DEFAULT_NEW_PER_DAY = 10
MAX_ANSWER_CHARS = 100
VIETNAM = timezone(timedelta(hours=7))  # a learner's "today" starts at midnight in Vietnam (no DST)


@dataclass(frozen=True)
class SessionEntry:
    item: vitems.LearnerItem
    is_new: bool
    card: vitems.WordCard | None  # shown before the first question, for new words only
    due_at: datetime | None


@dataclass(frozen=True)
class Session:
    entries: list[SessionEntry]
    due: int  # cards due now (before the limit)
    new_today: int
    new_left_today: int


@dataclass(frozen=True)
class AnswerResult:
    correct: bool
    accepted: str  # the key, shown when the answer was wrong
    card: vitems.WordCard  # the word, as feedback
    due_at: datetime
    trace: DecisionTrace


def start_of_day(now: datetime) -> datetime:
    local = now.astimezone(VIETNAM)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


class VocabPractice:
    def __init__(self, pool: Callable[[], ConnectionPool], lists_dir: Path) -> None:
        self.pool = pool
        self.lists_dir = lists_dir
        self._lists: dict[str, WordList] = {}

    def wordlist(self, slug: str) -> WordList:
        if slug in self._lists:
            return self._lists[slug]
        path = self.lists_dir / f"{slug}.yaml"
        if not slug.replace("-", "").isalnum() or not path.is_file():
            raise HTTPException(404, "Không tìm thấy danh sách từ vựng.")
        self._lists[slug] = load_wordlist(path)
        return self._lists[slug]

    def _learner(self, conn: psycopg.Connection[Any], learner_id: str) -> UUID:
        learner = learner_uuid(learner_id)
        if not conn.execute(
            "select id from learners where id=%s for update", (learner,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy người học.")
        return learner

    def _subject(self, conn: psycopg.Connection[Any], wl: WordList) -> UUID:
        row = conn.execute(
            "insert into subjects(slug,name_vi,name_en) values (%s,%s,%s) "
            "on conflict(slug) do update set name_vi=excluded.name_vi,name_en=excluded.name_en "
            "returning id",
            (f"vocabulary-{wl.slug}", wl.title_vi, wl.title_en),
        ).fetchone()
        assert row is not None
        return row[0]  # type: ignore[no-any-return]

    # --- a session -----------------------------------------------------------------------------

    def session(
        self,
        learner_id: str,
        list_slug: str,
        *,
        limit: int = DEFAULT_LIMIT,
        new_limit: int = DEFAULT_NEW_PER_DAY,
        max_level: str = "C1",
        now: datetime | None = None,
    ) -> Session:
        wl = self.wordlist(list_slug)
        now = now or datetime.now(UTC)
        top = LEVELS.index(max_level)  # the route validates the level
        with self.pool().connection() as conn:
            learner = self._learner(conn, learner_id)
            cards = {
                row[0]: (row[1], row[2])
                for row in conn.execute(
                    "select word_key, reviews, due_at from vocab_cards "
                    "where learner_id=%s and list_slug=%s",
                    (learner, list_slug),
                )
            }
            new_today = conn.execute(
                "select count(*) from vocab_cards where learner_id=%s and list_slug=%s "
                "and created_at >= %s",
                (learner, list_slug, start_of_day(now)),
            ).fetchone()
        assert new_today is not None
        due = sorted(
            ((key, reviews, due_at) for key, (reviews, due_at) in cards.items() if due_at <= now),
            key=lambda c: (c[2], c[0]),
        )
        entries = []
        for key, reviews, due_at in due[:limit]:
            word = wl.get(key)
            if word is None:  # the list changed since the card was made: skip, never crash
                continue
            kind, n = vitems.pick(word, reviews)
            entries.append(
                SessionEntry(
                    vitems.learner_view(vitems.build_item(wl, word, kind, n)), False, None, due_at
                )
            )
        new_left = max(new_limit - new_today[0], 0)
        fresh = [w for w in wl.words if w.key not in cards and wl.level_index(w) <= top]
        for word in fresh[: min(new_left, max(limit - len(entries), 0))]:
            kind, n = vitems.pick(word, 0)
            item = vitems.build_item(wl, word, kind, n)
            entries.append(SessionEntry(vitems.learner_view(item), True, vitems.card(word), None))
        return Session(entries, len(due), new_today[0], new_left)

    # --- an answer -----------------------------------------------------------------------------

    def answer(
        self, learner_id: str, item_id: str, answer: str, *, now: datetime | None = None
    ) -> AnswerResult:
        if len(answer) > MAX_ANSWER_CHARS:
            raise HTTPException(422, "Câu trả lời quá dài.")
        try:
            list_slug, key, kind, n = vitems.parse_item_id(item_id)
        except ValueError:
            raise HTTPException(422, "Mã câu hỏi không hợp lệ.") from None
        wl = self.wordlist(list_slug)
        word = wl.get(key)
        if word is None:
            raise HTTPException(404, "Không tìm thấy từ này.")
        try:
            item = vitems.build_item(wl, word, kind, n)
        except ValueError:
            raise HTTPException(404, "Không tìm thấy câu hỏi này.") from None
        correct = vitems.grade(item, answer)
        now = now or datetime.now(UTC)
        with self.pool().connection() as conn, conn.transaction():
            learner = self._learner(conn, learner_id)
            subject = self._subject(conn, wl)
            row = conn.execute(
                "select fsrs_state, reviews, lapses from vocab_cards "
                "where learner_id=%s and list_slug=%s and word_key=%s for update",
                (learner, list_slug, key),
            ).fetchone()
            state = row[0] if row else srs.new_card(now).state
            review, trace = srs.review_traced(
                state, correct, now, concept_slug=key, item_id=item.id
            )
            reviews = (row[1] if row else 0) + 1
            lapses = (row[2] if row else 0) + (0 if correct else 1)
            conn.execute(
                "insert into vocab_cards(learner_id,list_slug,word_key,fsrs_state,due_at,"
                "reviews,lapses,created_at) values (%s,%s,%s,%s,%s,%s,%s,%s) "
                "on conflict(learner_id,list_slug,word_key) do update set "
                "fsrs_state=excluded.fsrs_state,due_at=excluded.due_at,"
                "reviews=excluded.reviews,lapses=excluded.lapses",
                (
                    learner,
                    list_slug,
                    key,
                    Jsonb(dict(review.state)),
                    review.due_at,
                    reviews,
                    lapses,
                    now,  # the schedule's clock, so "new today" never mixes two clocks
                ),
            )
            conn.execute(
                "insert into vocab_reviews(learner_id,list_slug,word_key,item_kind,correct,answer,"
                "due_at,answered_at) values (%s,%s,%s,%s,%s,%s,%s,%s)",
                (learner, list_slug, key, kind, correct, answer.strip(), review.due_at, now),
            )
            save_trace(conn, learner, subject, trace)
        return AnswerResult(correct, item.accepted[0], vitems.card(word), review.due_at, trace)
