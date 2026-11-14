"""The grammar roadmap: level test, milestone tests, quick checks and practice (specs/level-test).

The engine decides (`engine.milestones`, `engine.bkt`); this module loads the course and its items,
keeps the learner's state in the database and turns decisions into questions. A milestone test, the
quick checks after it and practice on one hidden node are all a fixed list of items answered in
order (`grammar_runs`); the level test is adaptive (`level_tests`). Draft items are served only to
the learners in `DRAFT_ITEM_LEARNERS`, labelled; everyone else sees reviewed items only.
"""

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import psycopg
import yaml  # type: ignore[import-untyped]
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.curriculum.course import CourseSpec, load_course
from app.curriculum.items import GrammarItem, ItemBank, load_items, round_robin
from app.curriculum.levels import ielts_range_vi, lower
from app.curriculum.roadmap import build_roadmap
from app.curriculum.store import sync_course
from app.engine import bkt
from app.engine.graph import UNSEEN_P_KNOWN
from app.engine.milestones import (
    ASSUMED_KNOWN,
    LEVELS,
    MIN_TEST_SIZE,
    NodeAnswer,
    Roadmap,
    known_milestones,
    level_from,
    level_test_next,
    milestone_outcome,
    milestone_status,
    next_to_learn,
    questions_in_test,
    seed_from_level_test,
    up_to,
    vocab_level,
)
from app.engine.placement import Answer
from app.engine.trace import DecisionTrace
from app.services.backend import learner_uuid, save_trace
from app.services.learning import save_mastery
from app.vocabulary import items as vitems
from app.vocabulary.wordlist import WordList, load_wordlist

PRACTICE_SIZE = 3
CHECKS_PER_NODE = 2
VOCAB_TIERS = ("A2", "B1", "B2", "C1")
VOCAB_PER_TIER = 3
VOCAB_PASS = 2


@dataclass(frozen=True)
class Question:
    item_id: str
    prompt: str
    options: list[str]
    draft: bool  # shown as "Bản nháp"
    number: int  # 1-based position in its run or test
    total: int | None  # None for the adaptive level test


@dataclass
class Step:
    """What the learner sees after an action: the next question, and what was decided."""

    question: Question | None
    run_id: str | None = None  # the run or level test the question belongs to
    kind: str | None = None
    finished: dict[str, Any] | None = None  # outcome of a run or the level test result
    traces: list[DecisionTrace] = field(default_factory=list)
    feedback: dict[str, Any] | None = None  # the last answer of a run: right or wrong, and why


@dataclass(frozen=True)
class Bundle:
    course: CourseSpec
    roadmap: Roadmap
    bank: ItemBank
    misconceptions_vi: dict[str, str] = field(default_factory=dict)


def load_misconceptions(path: Path) -> dict[str, str]:
    """Vietnamese explanations of misconception ids (data/items/misconceptions.vi.yaml)."""
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found = raw.get("misconceptions", {})
    if not isinstance(found, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in found.items()
    ):
        raise ValueError(f"{path}: misconceptions must map ids to text")
    return found


class GrammarService:
    def __init__(
        self,
        pool: Callable[[], ConnectionPool],
        courses_dir: Path,
        items_dir: Path,
        vocab_dir: Path,
        draft_learners: str = "",
        vocab_list: str = "core-seed",
    ) -> None:
        self.pool = pool
        self.courses_dir, self.items_dir, self.vocab_dir = courses_dir, items_dir, vocab_dir
        self.vocab_list = vocab_list
        self.draft_learners = {
            learner_uuid(x.strip()) for x in draft_learners.split(",") if x.strip()
        }
        self._bundles: dict[str, Bundle] = {}
        self._synced: dict[str, tuple[UUID, dict[str, UUID]]] = {}
        self._lock = threading.Lock()

    # --- loading ---------------------------------------------------------------------------

    def bundle(self, slug: str) -> Bundle:
        if slug in self._bundles:
            return self._bundles[slug]
        course_path = self.courses_dir / f"{slug}.yaml"
        items_path = self.items_dir / f"{slug}.yaml"
        if not slug.replace("-", "").isalnum() or not course_path.is_file():
            raise HTTPException(404, "Không tìm thấy khóa học.")
        if not items_path.is_file():
            raise HTTPException(404, "Khóa học này chưa có câu hỏi.")
        course = load_course(course_path)
        bundle = Bundle(
            course,
            build_roadmap(course),
            load_items(items_path, course),
            load_misconceptions(self.items_dir / "misconceptions.vi.yaml"),
        )
        self._bundles[slug] = bundle
        return bundle

    def wordlist(self) -> WordList:
        return load_wordlist(self.vocab_dir / f"{self.vocab_list}.yaml")

    def _synced_ids(
        self, conn: psycopg.Connection[Any], course: CourseSpec
    ) -> tuple[UUID, dict[str, UUID]]:
        with self._lock:
            if course.slug not in self._synced:
                ids = sync_course(conn, course)
                row = conn.execute(
                    "select id from subjects where slug=%s", (course.slug,)
                ).fetchone()
                assert row is not None
                self._synced[course.slug] = (row[0], ids)
            return self._synced[course.slug]

    def _learner(self, conn: psycopg.Connection[Any], learner_id: str) -> UUID:
        learner = learner_uuid(learner_id)
        if not conn.execute(
            "select id from learners where id=%s for update", (learner,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy người học.")
        return learner

    # --- learner state ---------------------------------------------------------------------

    def _p_known(
        self, conn: psycopg.Connection[Any], learner: UUID, course: str
    ) -> dict[str, float]:
        rows = conn.execute(
            "select c.slug, m.p_known from mastery m join concepts c on c.id=m.concept_id "
            "join subjects s on s.id=c.subject_id where m.learner_id=%s and s.slug=%s",
            (learner, course),
        ).fetchall()
        return {r[0]: float(r[1]) for r in rows}

    def _unaided(self, conn: psycopg.Connection[Any], learner: UUID, course: str) -> dict[str, int]:
        rows = conn.execute(
            "select node, count(*) from grammar_answers where learner_id=%s and course=%s "
            "and correct group by node",
            (learner, course),
        ).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def _seen(self, conn: psycopg.Connection[Any], learner: UUID, course: str) -> set[str]:
        rows = conn.execute(
            "select distinct item_id from grammar_answers where learner_id=%s and course=%s",
            (learner, course),
        ).fetchall()
        return {r[0] for r in rows}

    def _servable(self, b: Bundle, learner: UUID, node: str, seen: set[str]) -> list[str]:
        """Items for a hidden node this learner may see, never-answered ones first."""
        items = b.bank.for_node(node, include_drafts=learner in self.draft_learners)
        return [i.id for i in sorted(items, key=lambda i: i.id in seen)]

    def _question(self, item: GrammarItem, number: int, total: int | None) -> Question:
        return Question(
            item.id, item.prompt, [o.text for o in item.shuffled()], item.status == "draft",
            number, total,
        )  # fmt: skip

    # --- the level test --------------------------------------------------------------------

    def _level_roadmap(self, b: Bundle, target: str | None) -> Roadmap:
        return up_to(b.roadmap, target) if target else b.roadmap

    def _caps(self, b: Bundle, rm: Roadmap, learner: UUID) -> dict[str, int]:
        drafts = learner in self.draft_learners
        return {
            m: sum(len(b.bank.for_node(n, include_drafts=drafts)) for n in rm.hidden[m])
            for m in rm.level
        }

    def _level_item(
        self, b: Bundle, rm: Roadmap, learner: UUID, milestone: str, used: set[str]
    ) -> str:
        lists = [self._servable(b, learner, n, set()) for n in rm.hidden[milestone]]
        order = round_robin(lists, sum(len(x) for x in lists))
        return next(i for i in order if i not in used)

    def start_level_test(
        self, learner_id: str, course_slug: str, target: str | None, *, now: datetime | None = None
    ) -> Step:
        b = self.bundle(course_slug)
        rm = self._level_roadmap(b, target)
        with self.pool().connection() as conn, conn.transaction():
            learner = self._learner(conn, learner_id)
            caps = self._caps(b, rm, learner)
            if not any(caps.values()):
                raise HTTPException(409, "Chưa có câu hỏi nào được duyệt cho bài kiểm tra này.")
            milestone, trace = level_test_next(rm, [], asks_per_milestone=caps, now=now)
            assert milestone is not None
            item_id = self._level_item(b, rm, learner, milestone, set())
            row = conn.execute(
                "insert into level_tests(learner_id,course,target,pending) values (%s,%s,%s,%s) "
                "returning id",
                (learner, course_slug, target,
                 Jsonb({"part": "grammar", "slug": milestone, "item_id": item_id})),
            ).fetchone()  # fmt: skip
        assert row is not None
        item = b.bank.get(item_id)
        assert item is not None
        return Step(self._question(item, 1, None), str(row[0]), "level", traces=[trace])

    def answer_level_test(
        self, learner_id: str, test_id: str, item_id: str, answer: str, *,
        now: datetime | None = None,
    ) -> Step:  # fmt: skip
        now = now or datetime.now(UTC)
        with self.pool().connection() as conn, conn.transaction():
            learner = self._learner(conn, learner_id)
            row = conn.execute(
                "select course,target,phase,answers,pending from level_tests "
                "where id=%s and learner_id=%s for update",
                (_uuid(test_id), learner),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Không tìm thấy bài kiểm tra.")
            course_slug, target, phase, answers, pending = row
            if phase == "done" or pending is None:
                raise HTTPException(409, "Bài kiểm tra đã kết thúc.")
            if pending["item_id"] != item_id:
                raise HTTPException(409, "Câu hỏi này không phải câu đang làm.")
            b = self.bundle(course_slug)
            rm = self._level_roadmap(b, target)
            if pending["part"] == "grammar":
                item = b.bank.get(item_id)
                assert item is not None
                correct = answer == item.key
                answers.append({"part": "grammar", "slug": pending["slug"], "item_id": item_id,
                                "correct": correct})  # fmt: skip
                self._log(conn, learner, course_slug, item, correct, answer, "level", now)
            else:
                correct = vitems.grade(_vocab_item(self.wordlist(), item_id), answer)
                answers.append({"part": "vocab", "slug": pending["tier"], "item_id": item_id,
                                "correct": correct})  # fmt: skip
            step = self._advance_level(conn, b, rm, learner, str(test_id), answers, now)
        return step

    def _advance_level(
        self, conn: psycopg.Connection[Any], b: Bundle, rm: Roadmap, learner: UUID,
        test_id: str, answers: list[dict[str, Any]], now: datetime,
    ) -> Step:  # fmt: skip
        grammar = [Answer(a["slug"], a["correct"], a["item_id"]) for a in answers
                   if a["part"] == "grammar"]  # fmt: skip
        vocab = [a for a in answers if a["part"] == "vocab"]
        traces: list[DecisionTrace] = []
        if not vocab:
            caps = self._caps(b, rm, learner)
            milestone, trace = level_test_next(rm, grammar, asks_per_milestone=caps, now=now)
            traces.append(trace)
            if milestone is not None:
                used = {a.item_id for a in grammar if a.item_id}
                item_id = self._level_item(b, rm, learner, milestone, used)
                pending = {"part": "grammar", "slug": milestone, "item_id": item_id}
                return self._pend(conn, b, test_id, answers, traces, len(answers) + 1, pending)
        tier, word_item = self._next_vocab(vocab)
        if tier is not None and word_item is not None:
            pending = {"part": "vocab", "slug": word_item, "tier": tier, "item_id": word_item}
            return self._pend(conn, b, test_id, answers, traces, len(answers) + 1, pending,
                              vocab=True)  # fmt: skip
        return self._finish_level(
            conn, b, rm, learner, test_id, answers, grammar, vocab, traces, now
        )

    def _next_vocab(self, vocab: list[dict[str, Any]]) -> tuple[str | None, str | None]:
        wl = self.wordlist()
        for tier in VOCAB_TIERS:
            done = [a for a in vocab if a["slug"] == tier]
            right = sum(a["correct"] for a in done)
            wrong = len(done) - right
            if right >= VOCAB_PASS:
                continue  # tier passed: go up
            words = [w for w in wl.words if w.level == tier][:VOCAB_PER_TIER]
            if wrong > len(words) - VOCAB_PASS or len(done) >= len(words):
                return None, None  # tier failed or exhausted: stop
            word = words[len(done)]
            return tier, vitems.item_id(wl.slug, word.key, "meaning", 0)
        return None, None

    def _pend(
        self, conn: psycopg.Connection[Any], b: Bundle, test_id: str, answers: list[dict[str, Any]],
        traces: list[DecisionTrace], number: int, pending: dict[str, Any], *, vocab: bool = False,
    ) -> Step:  # fmt: skip
        conn.execute(
            "update level_tests set answers=%s, pending=%s, phase=%s where id=%s",
            (Jsonb(answers), Jsonb(pending), "vocab" if vocab else "grammar", _uuid(test_id)),
        )
        if vocab:
            v = _vocab_item(self.wordlist(), pending["item_id"])
            q = Question(v.id, v.prompt, list(v.options or ()), False, number, None)
        else:
            item = b.bank.get(pending["item_id"])
            assert item is not None
            q = self._question(item, number, None)
        return Step(q, test_id, "level", traces=traces)

    def _finish_level(
        self, conn: psycopg.Connection[Any], b: Bundle, rm: Roadmap, learner: UUID, test_id: str,
        answers: list[dict[str, Any]], grammar: Sequence[Answer], vocab: list[dict[str, Any]],
        traces: list[DecisionTrace], now: datetime,
    ) -> Step:  # fmt: skip
        known = known_milestones(rm, grammar)
        grammar_level = level_from(rm, known)
        results = {t: (sum(a["correct"] for a in vocab if a["slug"] == t),
                       sum(1 for a in vocab if a["slug"] == t)) for t in VOCAB_TIERS}  # fmt: skip
        vocab_lvl = vocab_level(results, pass_mark=VOCAB_PASS)
        shown = lower(grammar_level, vocab_lvl)  # type: ignore[arg-type]
        subject, ids = self._synced_ids(conn, b.course)
        current = self._p_known(conn, learner, b.course.slug)
        for node, p in seed_from_level_test(rm, known).items():
            if current.get(node, UNSEEN_P_KNOWN) < p:
                save_mastery(conn, learner, ids[node], p)
        for t in traces:
            save_trace(conn, learner, subject, t)
        result = {
            "grammar_level": grammar_level,
            "vocab_level": vocab_lvl,
            "ielts_vi": ielts_range_vi(shown),
            "known_milestones": sorted(known),
            "questions": len(answers),
        }
        conn.execute(
            "update level_tests set answers=%s, pending=null, phase='done', result=%s, "
            "finished_at=%s where id=%s",
            (Jsonb(answers), Jsonb(result), now, _uuid(test_id)),
        )
        return Step(None, test_id, "level", finished=result, traces=traces)

    # --- the roadmap -----------------------------------------------------------------------

    def roadmap(self, learner_id: str, course_slug: str) -> dict[str, Any]:
        b = self.bundle(course_slug)
        rm = b.roadmap
        with self.pool().connection() as conn:
            learner = self._learner(conn, learner_id)
            p = self._p_known(conn, learner, course_slug)
            unaided = self._unaided(conn, learner, course_slug)
            last = conn.execute(
                "select result from level_tests where learner_id=%s and course=%s "
                "and phase='done' order by finished_at desc limit 1",
                (learner, course_slug),
            ).fetchone()
        status = milestone_status(rm, p, unaided)
        settled = {m for m, s in status.items() if s in ("known", "mastered")}
        next_milestone = next(
            (m for m in rm.milestones.order
             if m not in settled and all(x in settled for x in rm.milestones.parents[m])),
            None,
        )  # fmt: skip
        opened = [n for m, s in status.items() if s == "partial" for n in rm.hidden[m]
                  if p.get(n, UNSEEN_P_KNOWN) < ASSUMED_KNOWN]  # fmt: skip
        learn, why = next_to_learn(rm, opened, p) if opened else (None, None)
        return {
            "course": course_slug,
            "level_test": last[0] if last else None,
            "milestones": [
                {
                    "slug": m,
                    "name_vi": rm.graph.name_vi(m),
                    "level": rm.level[m],
                    "status": status[m],
                    "needs": list(rm.milestones.parents[m]),
                    "hidden": [
                        {
                            "slug": n,
                            "name_vi": rm.graph.name_vi(n),
                            "p_known": round(p.get(n, UNSEEN_P_KNOWN), 3),
                            "known": p.get(n, UNSEEN_P_KNOWN) >= ASSUMED_KNOWN,
                        }
                        for n in rm.hidden[m]
                    ],
                }
                for m in rm.milestones.order
            ],
            "next_milestone": next_milestone,
            "learn_next": learn,
            "learn_next_trace": why,
        }

    # --- runs: milestone test, quick checks, practice --------------------------------------

    def start_run(
        self, learner_id: str, course_slug: str, kind: Literal["milestone", "practice"], target: str
    ) -> Step:
        b = self.bundle(course_slug)
        rm = b.roadmap
        with self.pool().connection() as conn, conn.transaction():
            learner = self._learner(conn, learner_id)
            seen = self._seen(conn, learner, course_slug)
            if kind == "milestone":
                if target not in rm.hidden:
                    raise HTTPException(404, "Không tìm thấy cột mốc.")
                lists = [self._servable(b, learner, n, seen) for n in rm.hidden[target]]
                items = round_robin(lists, questions_in_test(len(rm.hidden[target])))
                if len(items) < MIN_TEST_SIZE:
                    raise HTTPException(409, "Cột mốc này chưa đủ câu hỏi được duyệt.")
            else:
                if target not in rm.hidden_nodes:
                    raise HTTPException(404, "Không tìm thấy phần học này.")
                items = self._servable(b, learner, target, seen)[:PRACTICE_SIZE]
                if not items:
                    raise HTTPException(409, "Phần học này chưa có câu hỏi được duyệt.")
            run_id = self._insert_run(conn, learner, course_slug, kind, target, items)
        first = b.bank.get(items[0])
        assert first is not None
        return Step(self._question(first, 1, len(items)), run_id, kind)

    def _insert_run(
        self, conn: psycopg.Connection[Any], learner: UUID, course: str, kind: str, target: str,
        items: list[str],
    ) -> str:  # fmt: skip
        row = conn.execute(
            "insert into grammar_runs(learner_id,course,kind,target,item_ids) "
            "values (%s,%s,%s,%s,%s) returning id",
            (learner, course, kind, target, Jsonb(items)),
        ).fetchone()
        assert row is not None
        return str(row[0])

    def _log(
        self, conn: psycopg.Connection[Any], learner: UUID, course: str, item: GrammarItem,
        correct: bool, answer: str, context: str, now: datetime,
    ) -> None:  # fmt: skip
        conn.execute(
            "insert into grammar_answers(learner_id,course,node,item_id,correct,misconception,"
            "context,answered_at) values (%s,%s,%s,%s,%s,%s,%s,%s)",
            (learner, course, item.node, item.id, correct,
             None if correct else item.misconception_for(answer), context, now),
        )  # fmt: skip

    def answer_run(
        self, learner_id: str, run_id: str, item_id: str, answer: str, *,
        now: datetime | None = None,
    ) -> Step:  # fmt: skip
        now = now or datetime.now(UTC)
        with self.pool().connection() as conn, conn.transaction():
            learner = self._learner(conn, learner_id)
            row = conn.execute(
                "select course,kind,target,item_ids,answers,finished_at from grammar_runs "
                "where id=%s and learner_id=%s for update",
                (_uuid(run_id), learner),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Không tìm thấy lượt làm bài.")
            course_slug, kind, target, item_ids, answers, finished = row
            if finished is not None:
                raise HTTPException(409, "Lượt làm bài đã kết thúc.")
            if item_ids[len(answers)] != item_id:
                raise HTTPException(409, "Câu hỏi này không phải câu đang làm.")
            b = self.bundle(course_slug)
            item = b.bank.get(item_id)
            assert item is not None
            subject, ids = self._synced_ids(conn, b.course)
            correct = answer == item.key
            misconception = None if correct else item.misconception_for(answer)
            self._log(conn, learner, course_slug, item, correct, answer, kind, now)
            p = self._p_known(conn, learner, course_slug).get(item.node, UNSEEN_P_KNOWN)
            unaided = self._unaided(conn, learner, course_slug).get(item.node, 0)
            p_new, trace = bkt.update_traced(
                p, correct, bkt.DEFAULT_PARAMS["mcq"], concept_slug=item.node, now=now,
                item_id=item.id, misconception=misconception, unaided_correct=unaided,
            )  # fmt: skip
            save_mastery(conn, learner, ids[item.node], p_new)
            save_trace(conn, learner, subject, trace)
            answers.append({"item_id": item_id, "node": item.node, "correct": correct,
                            "misconception": misconception})  # fmt: skip
            traces = [trace]
            feedback = {
                "correct": correct,
                "key": item.key,
                "misconception": misconception,
                "misconception_vi": b.misconceptions_vi.get(misconception)
                if misconception
                else None,
            }
            if len(answers) < len(item_ids):
                conn.execute(
                    "update grammar_runs set answers=%s where id=%s",
                    (Jsonb(answers), _uuid(run_id)),
                )
                nxt = b.bank.get(item_ids[len(answers)])
                assert nxt is not None
                step = Step(self._question(nxt, len(answers) + 1, len(item_ids)), run_id, kind,
                            traces=traces)  # fmt: skip
            else:
                step = self._finish_run(conn, b, learner, run_id, kind, target, item_ids,
                                        answers, traces, subject, ids, now)  # fmt: skip
            step.feedback = feedback
            return step

    def _finish_run(
        self, conn: psycopg.Connection[Any], b: Bundle, learner: UUID, run_id: str, kind: str,
        target: str, item_ids: list[str], answers: list[dict[str, Any]],
        traces: list[DecisionTrace], subject: UUID, ids: dict[str, UUID], now: datetime,
    ) -> Step:  # fmt: skip
        rm = b.roadmap
        p = self._p_known(conn, learner, b.course.slug)
        outcome: dict[str, Any]
        follow_up: Step | None = None
        if kind == "milestone":
            node_answers = [NodeAnswer(a["node"], a["correct"], a["item_id"], a["misconception"])
                            for a in answers]  # fmt: skip
            out = milestone_outcome(rm, target, node_answers, p, now=now)
            for node, value in out.raised.items():
                if p.get(node, UNSEEN_P_KNOWN) < value:
                    save_mastery(conn, learner, ids[node], value)
            assert out.trace is not None
            save_trace(conn, learner, subject, out.trace)
            traces.append(out.trace)
            outcome = {"result": out.result, "opened": list(out.opened)}
            if out.opened:
                seen = self._seen(conn, learner, b.course.slug) | set(item_ids)
                lists = [[i for i in self._servable(b, learner, n, seen) if i not in item_ids]
                         [:CHECKS_PER_NODE] for n in out.opened]  # fmt: skip
                checks = [i for xs in lists for i in xs]
                if checks:
                    check_id = self._insert_run(conn, learner, b.course.slug, "checks", target,
                                                checks)  # fmt: skip
                    first = b.bank.get(checks[0])
                    assert first is not None
                    follow_up = Step(self._question(first, 1, len(checks)), check_id, "checks")
                else:
                    outcome.update(self._learn_next(rm, list(out.opened), p, subject, conn,
                                                    learner, traces, now))  # fmt: skip
        elif kind == "checks":
            opened = sorted({a["node"] for a in answers})
            outcome = self._learn_next(rm, opened, p, subject, conn, learner, traces, now)
        else:
            unaided = self._unaided(conn, learner, b.course.slug).get(target, 0)
            value = p.get(target, UNSEEN_P_KNOWN)
            outcome = {"node": target, "p_known": round(value, 3),
                       "mastered": bkt.is_confirmed_mastery(value, unaided)}  # fmt: skip
        conn.execute(
            "update grammar_runs set answers=%s, outcome=%s, finished_at=%s where id=%s",
            (Jsonb(answers), Jsonb(outcome), now, _uuid(run_id)),
        )
        if follow_up is not None:
            follow_up.finished = outcome
            follow_up.traces = traces
            return follow_up
        return Step(None, run_id, kind, finished=outcome, traces=traces)

    def _learn_next(
        self, rm: Roadmap, opened: list[str], p: dict[str, float], subject: UUID,
        conn: psycopg.Connection[Any], learner: UUID, traces: list[DecisionTrace], now: datetime,
    ) -> dict[str, Any]:  # fmt: skip
        node, trace = next_to_learn(rm, opened, p, now=now)
        if trace is not None:
            save_trace(conn, learner, subject, trace)
            traces.append(trace)
        return {"learn_next": node}


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(404, "Không tìm thấy.") from None


def _vocab_item(wl: WordList, item_id: str) -> vitems.Item:
    _, key, kind, n = vitems.parse_item_id(item_id)
    word = wl.get(key)
    assert word is not None
    return vitems.build_item(wl, word, kind, n)


__all__ = ["LEVELS", "GrammarService", "Question", "Step"]
