"""Database adapter for P3 routes; all learning decisions remain in P1's engine."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import JsonValue

from app.api import learn
from app.config import get_settings
from app.engine import bkt, placement, srs
from app.engine.graph import UNSEEN_P_KNOWN, Graph
from app.engine.path import next_step
from app.engine.placer import Placer, make_placer
from app.engine.remediation import remediate
from app.engine.trace import DecisionTrace
from app.graders.mcq import Grade, Item
from app.services.attempts import remember, replay
from app.services.learning import (
    save_attempt,
    save_mastery,
    save_review,
    unaided_correct_counts,
)


def learner_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(422, "Mã người học không hợp lệ.") from None


def save_trace(
    conn: psycopg.Connection[Any],
    learner_id: UUID,
    subject_id: UUID,
    trace: DecisionTrace,
    attempt_id: UUID | None = None,
) -> None:
    conn.execute(
        "insert into decision_traces(learner_id,subject_id,attempt_id,concept_slug,kind,at,"
        "prior,posterior,evidence,rule,rule_vi,alternatives) values "
        "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            learner_id,
            subject_id,
            attempt_id,
            trace.concept_slug,
            trace.kind,
            trace.at,
            trace.prior,
            trace.posterior,
            Jsonb(trace.evidence.model_dump(mode="json")),
            trace.rule,
            trace.rule_vi,
            Jsonb([a.model_dump(mode="json") for a in trace.alternatives]),
        ),
    )


class LearningService:
    def __init__(self, pool: Callable[[], ConnectionPool], placer: Placer | None = None) -> None:
        self.pool = pool
        self.placer = placer or make_placer(get_settings().placement_strategy)

    def _context(
        self,
        conn: psycopg.Connection[Any],
        learner: str,
        subject: str,
    ) -> tuple[UUID, UUID, Graph, dict[str, UUID], dict[str, float]]:
        learner_id = learner_uuid(learner)
        # Serialize all state transitions for one learner, including first-ever mastery rows.
        if not conn.execute(
            "select id from learners where id=%s for update", (learner_id,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy người học.")
        from app.services.topic_readiness import require_published_topic

        require_published_topic(conn, subject)
        row = conn.execute("select id from subjects where slug=%s", (subject,)).fetchone()
        if row is None:
            raise HTTPException(404, "Không tìm thấy môn học.")
        subject_id = row[0]
        rows = conn.execute(
            "select c.slug,c.id,c.name_vi,m.p_known from concepts c left join mastery m "
            "on m.concept_id=c.id and m.learner_id=%s where c.subject_id=%s",
            (learner_id, subject_id),
        ).fetchall()
        edges = conn.execute(
            "select p.slug,c.slug from concept_edges e join concepts p on p.id=e.prerequisite_id "
            "join concepts c on c.id=e.concept_id where c.subject_id=%s",
            (subject_id,),
        ).fetchall()
        graph = Graph.from_edges([r[0] for r in rows], edges, {r[0]: r[2] for r in rows})
        if not graph.order:
            raise HTTPException(503, "Sơ đồ kiến thức chưa sẵn sàng.")
        return (
            learner_id,
            subject_id,
            graph,
            {r[0]: r[1] for r in rows},
            {r[0]: float(r[3]) for r in rows if r[3] is not None},
        )

    async def graph(self, learner_id: str, subject: str) -> learn.GraphResponse:
        return await asyncio.to_thread(self._graph, learner_id, subject)

    def _graph(self, learner_id: str, subject: str) -> learn.GraphResponse:
        with self.pool().connection() as conn:
            learner, subject_id, graph, _, mastery = self._context(conn, learner_id, subject)
            unaided = unaided_correct_counts(conn, learner, subject_id)
            return learn.GraphResponse(
                nodes=[
                    learn.GraphNode(
                        slug=s,
                        name_vi=graph.name_vi(s),
                        p_known=mastery.get(s, UNSEEN_P_KNOWN),
                        mastered=bkt.is_confirmed_mastery(
                            mastery.get(s, UNSEEN_P_KNOWN), unaided.get(s, 0)
                        ),
                    )
                    for s in graph.order
                ],
                edges=[
                    learn.GraphEdge(**{"from": p, "to": s})
                    for s in graph.order
                    for p in graph.parents[s]
                ],
            )

    @staticmethod
    def _items(conn: psycopg.Connection[Any], concept_id: UUID) -> list[Item]:
        # shortcut: retain the full validated item in payload until P4 hands off migration 0005.
        rows = conn.execute(
            "select payload from items where concept_id=%s and kind='mcq' "
            "and payload->>'status'='verified' order by id",
            (concept_id,),
        ).fetchall()
        return [Item.model_validate(r[0]) for r in rows]

    async def get_item(self, item_id: str) -> Item | None:
        return await asyncio.to_thread(self._get_item, item_id)

    def _get_item(self, item_id: str) -> Item | None:
        with self.pool().connection() as conn:
            row = conn.execute(
                "select payload from items where payload->>'id'=%s",
                (item_id,),
            ).fetchall()
            if len(row) > 1:
                raise HTTPException(503, "Mã câu hỏi bị trùng.")
            return Item.model_validate(row[0][0]) if row else None

    def resolve_answer(self, item: Item, answer: JsonValue) -> int:
        if type(answer) is not int or not 0 <= answer < len(item.options):
            raise ValueError("answer must be a zero-based option index")
        return answer

    async def placement(self, request: learn.LearnerSubject) -> learn.PlacementSelection:
        return await asyncio.to_thread(self._placement, request)

    def _placement(self, request: learn.LearnerSubject) -> learn.PlacementSelection:
        with self.pool().connection() as conn:
            learner, subject, graph, ids, _ = self._context(
                conn, request.learner_id, request.subject
            )
            rows = conn.execute(
                "select c.slug,a.is_correct,i.payload->>'id' from attempts a "
                "join items i on i.id=a.item_id join concepts c on c.id=i.concept_id "
                "where a.learner_id=%s and c.subject_id=%s and a.answer->>'phase'='placement' "
                "order by a.created_at,a.id",
                (learner, subject),
            ).fetchall()
            answers = [placement.Answer(*r) for r in rows]
            # A repeated question on a concept must be a new item: cap asks at the items held.
            available = {
                slug: n
                for slug, n in conn.execute(
                    "select c.slug,count(*) from items i join concepts c on c.id=i.concept_id "
                    "where c.subject_id=%s and i.kind='mcq' and i.payload->>'status'='verified' "
                    "group by c.slug",
                    (subject,),
                ).fetchall()
            }
            if not answers and not any(available.values()):
                # Nothing verified to ask: do not "finish" placement without evidence.
                raise HTTPException(503, "Chưa có câu hỏi đã kiểm chứng cho chủ đề này.")
            slug, trace = self.placer.next_question(graph, answers, available=available)
            selected = None
            if slug is not None:
                seen = {a.item_id for a in answers if a.slug == slug}
                fresh = [i for i in self._items(conn, ids[slug]) if i.id not in seen]
                if not fresh:
                    raise HTTPException(503, "Chưa có câu hỏi đã kiểm chứng cho khái niệm này.")
                selected = fresh[0]
            else:
                completed = conn.execute(
                    "select 1 from decision_traces where learner_id=%s and subject_id=%s "
                    "and kind='placement_step' and rule like 'placement.done.%%' limit 1",
                    (learner, subject),
                ).fetchone()
                # Only the first completion seeds placement; reconnects preserve later BKT work.
                if not completed:
                    for s, p in self.placer.seed_mastery(graph, answers).items():
                        save_mastery(conn, learner, ids[s], p)
            save_trace(conn, learner, subject, trace)
            return learn.PlacementSelection(
                item=selected,
                done=slug is None,
                gap_slug=self.placer.gap(graph, answers) if slug is None else None,
                trace=learn.DecisionTrace.model_validate(trace.model_dump()),
            )

    async def next_item(self, learner_id: str, subject: str) -> learn.NextSelection | None:
        return await asyncio.to_thread(self._next_item, learner_id, subject)

    def _next_item(self, learner_id: str, subject: str) -> learn.NextSelection | None:
        with self.pool().connection() as conn:
            learner, subject_id, graph, ids, mastery = self._context(conn, learner_id, subject)
            due: dict[str, datetime] = dict(
                conn.execute(
                    "select c.slug,r.due_at from review_cards r "
                    "join concepts c on c.id=r.concept_id "
                    "where r.learner_id=%s and c.subject_id=%s",
                    (learner, subject_id),
                ).fetchall()
            )
            origin = conn.execute(
                "select c.slug from attempts a join items i on i.id=a.item_id "
                "join concepts c on c.id=i.concept_id where a.learner_id=%s "
                "and c.subject_id=%s and not a.is_correct and a.answer->>'phase'='practice' "
                "order by a.created_at desc,a.id desc limit 1",
                (learner, subject_id),
            ).fetchone()
            resume_origin = (
                origin[0]
                if origin and not bkt.is_mastered(mastery.get(origin[0], UNSEEN_P_KNOWN))
                else None
            )
            available = {s: self._items(conn, ids[s]) for s in graph.order}
            step, trace = next_step(
                graph,
                mastery,
                now=datetime.now(UTC),
                due_reviews=due,
                resume_origin=resume_origin,
                available_concepts={s for s, items in available.items() if items},
            )
            if step.concept_slug is None:
                return None
            items = available[step.concept_slug]
            answered: dict[str, datetime] = dict(
                conn.execute(
                    "select i.payload->>'id',max(a.created_at) from attempts a "
                    "join items i on i.id=a.item_id where a.learner_id=%s "
                    "and i.concept_id=%s group by i.payload->>'id'",
                    (learner, ids[step.concept_slug]),
                ).fetchall()
            )
            unseen = [i for i in items if i.id not in answered]
            item = (
                min(unseen, key=lambda i: (abs(i.difficulty - step.target_difficulty), i.id))
                if unseen
                else min(items, key=lambda i: (answered[i.id], i.id))
            )
            save_trace(conn, learner, subject_id, trace)
            return learn.NextSelection(item=item, reason_vi=step.reason_vi)

    async def replay_attempt(self, request: learn.AttemptInput) -> learn.AttemptResponse | None:
        if request.client_attempt_id is None:
            return None

        def load() -> learn.AttemptResponse | None:
            with self.pool().connection() as conn:
                if not conn.execute(
                    "select id from learners where id=%s for update",
                    (learner_uuid(request.learner_id),),
                ).fetchone():
                    raise HTTPException(404, "Không tìm thấy người học.")
                return replay(conn, request)

        return await asyncio.to_thread(load)

    async def apply_attempt(
        self,
        request: learn.AttemptInput,
        item: Item,
        result: Grade,
    ) -> learn.AttemptUpdate | learn.AttemptResponse:
        return await asyncio.to_thread(self._apply_attempt, request, item, result)

    def _apply_attempt(
        self,
        request: learn.AttemptInput,
        item: Item,
        result: Grade,
    ) -> learn.AttemptUpdate | learn.AttemptResponse:
        with self.pool().connection() as conn:
            rows = conn.execute(
                "select i.id,c.slug,s.slug,i.payload from items i "
                "join concepts c on c.id=i.concept_id "
                "join subjects s on s.id=c.subject_id where i.payload->>'id'=%s",
                (item.id,),
            ).fetchall()
            if len(rows) != 1 or rows[0][3] != item.model_dump():
                raise HTTPException(409, "Câu hỏi đã thay đổi, hãy tải lại.")
            db_item_id, slug, subject_slug, _ = rows[0]
            learner, subject, graph, ids, mastery = self._context(
                conn,
                request.learner_id,
                subject_slug,
            )
            if cached := replay(conn, request):
                return cached
            now = datetime.now(UTC)
            # A pending placement trace identifies phase without accepting client-supplied flags.
            last = conn.execute(
                "select 1 from decision_traces where learner_id=%s and subject_id=%s "
                "and kind='placement_step' and rule like 'placement.done.%%' limit 1",
                (learner, subject),
            ).fetchone()
            phase = "placement" if not last else "practice"
            previous = conn.execute(
                "select a.answer->>'misconception' from attempts a join items i on i.id=a.item_id "
                "where a.learner_id=%s and i.concept_id=%s and not a.is_correct",
                (learner, ids[slug]),
            ).fetchall()
            misconception = (
                conn.execute(
                    "select id,description_vi from misconceptions where concept_id=%s "
                    "and (to_jsonb(misconceptions)->>'slug'=%s or description_vi=%s)",
                    (ids[slug], result.misconception, result.misconception),
                ).fetchone()
                if result.misconception
                else None
            )
            attempt = save_attempt(
                conn,
                learner_id=learner,
                item_id=db_item_id,
                answer={
                    "option_index": request.answer,
                    "hints_used": request.hints_used,
                    "misconception": result.misconception,
                    "phase": phase,
                },
                correct=result.correct,
                misconception_id=misconception[0] if misconception else None,
            )
            unaided = unaided_correct_counts(conn, learner, subject).get(slug, 0)
            p, trace = bkt.update_traced(
                mastery.get(slug, UNSEEN_P_KNOWN),
                result.correct,
                bkt.params_with_help(bkt.DEFAULT_PARAMS["mcq"], request.hints_used),
                concept_slug=slug,
                now=now,
                item_id=item.id,
                misconception=result.misconception,
                unaided_correct=unaided,
            )
            confirmed = bkt.is_confirmed_mastery(p, unaided)
            save_mastery(conn, learner, ids[slug], p)
            mastery[slug] = p
            traces = [trace]
            remediation = None
            if not result.correct and phase == "practice":
                plan, trace = remediate(
                    graph,
                    mastery,
                    slug,
                    now=now,
                    item_id=item.id,
                    misconception=result.misconception,
                    misconception_vi=misconception[1] if misconception else None,
                    earlier_misconceptions=[r[0] for r in previous if r[0] is not None],
                )
                remediation = plan.to_contract()
                traces.append(trace)
            card = conn.execute(
                "select fsrs_state from review_cards where learner_id=%s and concept_id=%s",
                (learner, ids[slug]),
            ).fetchone()
            if card or confirmed:
                state = card[0] if card else srs.new_card(now).state
                review, trace = srs.review_traced(
                    state,
                    result.correct,
                    now,
                    concept_slug=slug,
                    hints_used=request.hints_used,
                    item_id=item.id,
                )
                save_review(conn, learner, ids[slug], dict(review.state), review.due_at)
                traces.append(trace)
            for trace in traces:
                save_trace(conn, learner, subject, trace, attempt)
            update = learn.AttemptUpdate(
                p_known=p,
                mastered=confirmed,
                misconception_vi=misconception[1] if misconception else None,
                remediation=learn.Remediation.model_validate(remediation.model_dump())
                if remediation
                else None,
                traces=[learn.DecisionTrace.model_validate(t.model_dump()) for t in traces],
            )
            remember(conn, request, update, correct=result.correct)
            return update

    async def reviews_due(self, learner_id: str) -> learn.ReviewsResponse:
        return await asyncio.to_thread(self._reviews_due, learner_id)

    def _reviews_due(self, learner_id: str) -> learn.ReviewsResponse:
        with self.pool().connection() as conn:
            rows = conn.execute(
                "select c.slug,r.due_at from review_cards r join concepts c on c.id=r.concept_id "
                "where learner_id=%s and due_at<=now() order by due_at,c.slug",
                (learner_uuid(learner_id),),
            ).fetchall()
            return learn.ReviewsResponse(
                cards=[learn.ReviewCard(concept_slug=s, due_at=d) for s, d in rows]
            )

    async def exam_plan(self, request: learn.ExamInput) -> learn.ExamResponse:
        raise HTTPException(503, "Bộ lập kế hoạch ôn thi chưa được bàn giao.")
