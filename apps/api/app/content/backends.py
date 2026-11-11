"""Adapters for existing P3 HTTP ports; P1 computes and P2 persists learning state."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import JsonValue

from app.api import learn, topics, tutor
from app.config import get_settings
from app.content.gateway import Gateway
from app.content.integration import contract_item, tutor_text
from app.content.learning import GraphConfirmation, attempt_review, graph_confirmed
from app.content.pipeline import require_model_permission
from app.content.repository import Connection, Repository, StoredItem
from app.engine import bkt, path, placement, remediation
from app.engine.graph import Graph as EngineGraph
from app.engine.placer import Placer, make_placer
from app.engine.trace import DecisionTrace
from app.graders.mcq import Grade, grade
from app.graders.mcq import Item as GraderItem
from app.jobs.queue import enqueue
from app.schemas import KnowledgeGraph
from app.services.attempts import remember, replay
from app.services.learning import save_attempt, save_mastery, save_review
from app.services.topic_readiness import require_published_topic
from app.tutor.hints import HintAttempt, generate_hint_attempt, release_hint
from app.uploads.metadata import prepare_metadata
from app.uploads.reader import Document


def uid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(422, "Định danh không hợp lệ.") from None


def trace_dto(trace: DecisionTrace) -> learn.DecisionTrace:
    return learn.DecisionTrace.model_validate(trace.model_dump(mode="json"))


class LearningBackend:
    def __init__(
        self,
        repository: Repository,
        confirmation: GraphConfirmation | None = None,
        placer: Placer | None = None,
    ) -> None:
        self.repo = repository
        self.confirmation = confirmation
        self.placer = placer or make_placer(get_settings().placement_strategy)

    def _state(
        self, conn: Connection, learner: str, subject: str, *, require_confirmation: bool = True
    ) -> tuple[UUID, UUID, EngineGraph, dict[str, float]]:
        lid = uid(learner)
        if not conn.execute("select id from learners where id=%s for update", (lid,)).fetchone():
            raise HTTPException(404, "Không tìm thấy người học.")
        require_published_topic(conn, subject)
        sid = self.repo._subject(conn, subject)
        kg = self.repo.graph(conn, subject)
        if require_confirmation and not graph_confirmed(self.confirmation, learner, subject, kg):
            raise HTTPException(409, "Hãy xác nhận bản đồ kiến thức trước khi bắt đầu học.")
        graph = EngineGraph.from_contract(KnowledgeGraph.model_validate(kg.team_payload()))
        mastery = dict(
            conn.execute(
                "select c.slug,m.p_known from mastery m join concepts c on c.id=m.concept_id "
                "where m.learner_id=%s and c.subject_id=%s",
                (lid, sid),
            ).fetchall()
        )
        conn.execute(
            "insert into p4_learning_sessions(learner_id,subject_id) values(%s,%s) "
            "on conflict do nothing",
            (lid, sid),
        )
        return lid, sid, graph, mastery

    def _trace(
        self,
        conn: Connection,
        lid: UUID,
        sid: UUID,
        trace: DecisionTrace,
        attempt: UUID | None = None,
    ) -> None:
        conn.execute(
            "insert into decision_traces(learner_id,subject_id,attempt_id,concept_slug,kind,at,"
            "prior,posterior,evidence,rule,rule_vi,alternatives) values(%s,%s,"
            "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                lid,
                sid,
                attempt,
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

    def _pick(
        self,
        conn: Connection,
        subject: str,
        slug: str,
        learner: UUID,
        difficulty: float,
        *,
        allow_attempted: bool = False,
    ) -> StoredItem | None:
        candidates = []
        attempted = dict(
            conn.execute(
                "select item_id,max(created_at) from attempts where learner_id=%s group by item_id",
                (learner,),
            ).fetchall()
        )
        for key in self.repo.item_ids(conn, subject):
            bundle = self.repo.servable(conn, key)
            if (
                bundle
                and bundle.item.concept == slug
                and (allow_attempted or bundle.db_id not in attempted)
            ):
                candidates.append(bundle)
        return min(
            candidates,
            key=lambda b: (
                b.db_id in attempted,
                attempted.get(b.db_id, datetime.min.replace(tzinfo=UTC)),
                abs(b.item.difficulty - difficulty),
                b.item.id,
            ),
            default=None,
        )

    async def graph(self, learner_id: str, subject: str) -> learn.GraphResponse:
        def run() -> learn.GraphResponse:
            with self.repo.transaction() as conn:
                _, _, graph, mastery = self._state(
                    conn, learner_id, subject, require_confirmation=False
                )
                return learn.GraphResponse(
                    nodes=[
                        learn.GraphNode(
                            slug=s,
                            name_vi=graph.name_vi(s),
                            p_known=mastery.get(s, 0.2),
                            mastered=bkt.is_mastered(mastery.get(s, 0.2)),
                        )
                        for s in graph.order
                    ],
                    edges=[
                        learn.GraphEdge.model_validate({"from": p, "to": s})
                        for s in graph.order
                        for p in graph.parents[s]
                    ],
                )

        return await asyncio.to_thread(run)

    async def placement(self, request: learn.LearnerSubject) -> learn.PlacementSelection:
        def run() -> learn.PlacementSelection:
            with self.repo.transaction() as conn:
                lid, sid, graph, _ = self._state(conn, request.learner_id, request.subject)
                rows = conn.execute(
                    "select c.slug,a.is_correct,i.external_id from attempts a "
                    "join items i on i.id=a.item_id join concepts c on c.id=i.concept_id "
                    "where a.learner_id=%s and c.subject_id=%s and a.answer->>'phase'='placement' "
                    "order by a.created_at,a.id",
                    (lid, sid),
                ).fetchall()
                answers = [placement.Answer(slug=r[0], correct=r[1], item_id=r[2]) for r in rows]
                # A repeated question on a concept must be a new item: cap asks at the items held.
                available: dict[str, int] = {}
                for key in self.repo.item_ids(conn, request.subject):
                    bundle = self.repo.servable(conn, key)
                    if bundle:
                        available[bundle.item.concept] = available.get(bundle.item.concept, 0) + 1
                if not answers and not any(available.values()):
                    # Nothing verified to ask: do not "finish" placement without evidence.
                    raise HTTPException(503, "Chưa có câu hỏi đã kiểm chứng cho chủ đề này.")
                slug, trace = self.placer.next_question(graph, answers, available=available)
                if slug is None:
                    complete = conn.execute(
                        "select placement_complete from p4_learning_sessions "
                        "where learner_id=%s and subject_id=%s",
                        (lid, sid),
                    ).fetchone()
                    if complete and not complete[0]:
                        for concept, p in self.placer.seed_mastery(graph, answers).items():
                            cid = conn.execute(
                                "select id from concepts where subject_id=%s and slug=%s",
                                (sid, concept),
                            ).fetchone()
                            assert cid
                            save_mastery(conn, lid, cid[0], p)
                    conn.execute(
                        "update p4_learning_sessions set placement_complete=true,phase='practice',"
                        "pending_item=null where learner_id=%s and subject_id=%s",
                        (lid, sid),
                    )
                    self._trace(conn, lid, sid, trace)
                    return learn.PlacementSelection(
                        item=None,
                        done=True,
                        gap_slug=self.placer.gap(graph, answers),
                        trace=trace_dto(trace),
                    )
                bundle = self._pick(conn, request.subject, slug, lid, 0.5)
                if not bundle:
                    raise HTTPException(503, "Chưa có câu hỏi đã kiểm chứng cho khái niệm này.")
                conn.execute(
                    "update p4_learning_sessions set phase='placement',pending_item=%s "
                    "where learner_id=%s and subject_id=%s",
                    (bundle.db_id, lid, sid),
                )
                self._trace(conn, lid, sid, trace)
                return learn.PlacementSelection(
                    item=GraderItem.model_validate(contract_item(bundle.item).model_dump()),
                    done=False,
                    trace=trace_dto(trace),
                )

        return await asyncio.to_thread(run)

    async def next_item(self, learner_id: str, subject: str) -> learn.NextSelection | None:
        def run() -> learn.NextSelection | None:
            with self.repo.transaction() as conn:
                lid, sid, graph, mastery = self._state(conn, learner_id, subject)
                session = conn.execute(
                    "select remediation_origin from p4_learning_sessions "
                    "where learner_id=%s and subject_id=%s",
                    (lid, sid),
                ).fetchone()
                due = dict(
                    conn.execute(
                        "select c.slug,r.due_at from review_cards r join concepts c on c.i"
                        "d=r.concept_id "
                        "where r.learner_id=%s and c.subject_id=%s",
                        (lid, sid),
                    ).fetchall()
                )
                available = {
                    bundle.item.concept
                    for key in self.repo.item_ids(conn, subject)
                    if (bundle := self.repo.servable(conn, key)) is not None
                }
                step, trace = path.next_step(
                    graph,
                    mastery,
                    now=datetime.now(UTC),
                    resume_origin=session[0] if session else None,
                    due_reviews=due,
                    available_concepts=available,
                )
                if step.concept_slug is None:
                    return None
                bundle = self._pick(
                    conn,
                    subject,
                    step.concept_slug,
                    lid,
                    step.target_difficulty,
                    allow_attempted=True,
                )
                if bundle is None:
                    raise HTTPException(503, "Chưa có câu hỏi đã kiểm chứng phù hợp.")
                conn.execute(
                    "update p4_learning_sessions set phase='practice',pending_item=%s "
                    "where learner_id=%s and subject_id=%s",
                    (bundle.db_id, lid, sid),
                )
                self._trace(conn, lid, sid, trace)
                return learn.NextSelection(
                    item=GraderItem.model_validate(contract_item(bundle.item).model_dump()),
                    reason_vi=step.reason_vi,
                )

        return await asyncio.to_thread(run)

    async def get_item(self, item_id: str) -> GraderItem | None:
        def run() -> GraderItem | None:
            with self.repo.transaction() as conn:
                bundle = self.repo.servable(conn, item_id)
                return (
                    GraderItem.model_validate(contract_item(bundle.item).model_dump())
                    if bundle
                    else None
                )

        return await asyncio.to_thread(run)

    def resolve_answer(self, item: GraderItem, answer: JsonValue) -> int:
        if (
            isinstance(answer, bool)
            or not isinstance(answer, int)
            or not 0 <= answer < len(item.options)
        ):
            raise ValueError("Invalid option index")
        return answer

    async def replay_attempt(self, request: learn.AttemptInput) -> learn.AttemptResponse | None:
        if request.client_attempt_id is None:
            return None

        def load() -> learn.AttemptResponse | None:
            with self.repo.transaction() as conn:
                if not conn.execute(
                    "select id from learners where id=%s for update",
                    (uid(request.learner_id),),
                ).fetchone():
                    raise HTTPException(404, "Không tìm thấy người học.")
                return replay(conn, request)

        return await asyncio.to_thread(load)

    async def apply_attempt(
        self, request: learn.AttemptInput, item: GraderItem, result: Grade
    ) -> learn.AttemptUpdate | learn.AttemptResponse:
        def run() -> learn.AttemptUpdate | learn.AttemptResponse:
            with self.repo.transaction() as conn:
                # Use the same learner -> item lock order as selection.
                conn.execute(
                    "select id from learners where id=%s for update", (uid(request.learner_id),)
                ).fetchone()
                cached = replay(conn, request)
                if cached is not None:
                    return cached
                bundle = self.repo.servable(conn, item.id)
                if not bundle or contract_item(bundle.item).model_dump() != item.model_dump():
                    raise HTTPException(409, "Câu hỏi đã thay đổi; hãy tải lại.")
                lid, sid, graph, mastery = self._state(conn, request.learner_id, bundle.subject)
                session = conn.execute(
                    "select phase,pending_item from p4_learning_sessions where learner_id=%s "
                    "and subject_id=%s",
                    (lid, sid),
                ).fetchone()
                if not session or session[1] != bundle.db_id:
                    raise HTTPException(409, "Câu trả lời không thuộc bước học hiện tại.")
                if grade(item, request.answer) != result:
                    raise HTTPException(409, "Kết quả chấm đã thay đổi.")
                cid = conn.execute(
                    "select concept_id from items where id=%s", (bundle.db_id,)
                ).fetchone()
                assert cid
                earlier = [
                    r[0]
                    for r in conn.execute(
                        "select m.slug from attempts a join misconceptions m "
                        "on m.id=a.misconception_id join items i on i.id=a.item_id "
                        "where a.learner_id=%s and i.concept_id=%s order by a.created_at",
                        (lid, cid[0]),
                    )
                ]
                mid = (
                    conn.execute(
                        "select id,description_vi from misconceptions where concept_id=%s "
                        "and slug=%s",
                        (cid[0], result.misconception),
                    ).fetchone()
                    if result.misconception
                    else None
                )
                now = datetime.now(UTC)
                p, trace = bkt.update_traced(
                    mastery.get(item_concept := bundle.item.concept, 0.2),
                    result.correct,
                    bkt.DEFAULT_PARAMS["mcq"],
                    concept_slug=item_concept,
                    now=now,
                    item_id=item.id,
                    misconception=result.misconception,
                )
                aid = save_attempt(
                    conn,
                    learner_id=lid,
                    item_id=bundle.db_id,
                    answer={
                        "option_index": request.answer,
                        "hints_used": request.hints_used,
                        "phase": session[0],
                    },
                    correct=result.correct,
                    misconception_id=mid[0] if mid else None,
                )
                save_mastery(conn, lid, cid[0], p)
                mastery[item_concept] = p
                traces = [trace]
                plan = None
                if not result.correct and session[0] != "placement":
                    decision, rtrace = remediation.remediate(
                        graph,
                        mastery,
                        item_concept,
                        now=now,
                        item_id=item.id,
                        misconception=result.misconception,
                        misconception_vi=mid[1] if mid else None,
                        earlier_misconceptions=earlier,
                    )
                    plan = decision.to_contract()
                    traces.append(rtrace)
                    conn.execute(
                        "update p4_learning_sessions set remediation_origin=%s where learn"
                        "er_id=%s "
                        "and subject_id=%s",
                        (item_concept, lid, sid),
                    )
                card = conn.execute(
                    "select fsrs_state from review_cards where learner_id=%s and concept_id=%s",
                    (lid, cid[0]),
                ).fetchone()
                scheduled = attempt_review(
                    card[0] if card else None,
                    result.correct,
                    bkt.is_mastered(p),
                    now,
                    concept=item_concept,
                    item_id=item.id,
                    hints_used=request.hints_used,
                )
                if scheduled is not None:
                    reviewed, rtrace = scheduled
                    save_review(conn, lid, cid[0], dict(reviewed.state), reviewed.due_at)
                    traces.append(rtrace)
                for decision_trace in traces:
                    self._trace(conn, lid, sid, decision_trace, aid)
                conn.execute(
                    "update p4_learning_sessions set pending_item=null where learner_i"
                    "d=%s and subject_id=%s",
                    (lid, sid),
                )
                update = learn.AttemptUpdate(
                    p_known=p,
                    mastered=bkt.is_mastered(p),
                    misconception_vi=mid[1] if mid else None,
                    remediation=learn.Remediation.model_validate(plan.model_dump())
                    if plan
                    else None,
                    traces=[trace_dto(t) for t in traces],
                )
                remember(conn, request, update, correct=result.correct)
                return update

        return await asyncio.to_thread(run)

    async def reviews_due(self, learner_id: str) -> learn.ReviewsResponse:
        def run() -> learn.ReviewsResponse:
            with self.repo.transaction() as conn:
                rows = conn.execute(
                    "select c.slug,r.due_at from review_cards r join concepts c on c.i"
                    "d=r.concept_id "
                    "where learner_id=%s and due_at<=now() order by due_at",
                    (uid(learner_id),),
                )
                return learn.ReviewsResponse(
                    cards=[learn.ReviewCard(concept_slug=r[0], due_at=r[1]) for r in rows]
                )

        return await asyncio.to_thread(run)

    async def exam_plan(self, request: learn.ExamInput) -> learn.ExamResponse:
        raise HTTPException(503, "Lịch ôn trước kỳ thi chưa được tích hợp.")


class TopicsBackend:
    def __init__(self, repository: Repository) -> None:
        self.repo = repository

    async def enqueue(self, request: topics.TopicInput) -> topics.TopicResponse:
        def run() -> topics.TopicResponse:
            with self.repo.transaction() as conn:
                if (
                    request.upload_id
                    and not conn.execute(
                        "select id from uploads where id=%s and text_ok", (uid(request.upload_id),)
                    ).fetchone()
                ):
                    raise HTTPException(422, "Tài liệu chưa đọc được hoặc không tồn tại.")
                job = enqueue(conn, request.goal_vi or "Học theo tài liệu tải lên", request.tier)
                conn.execute(
                    "update topic_jobs set mode=%s,upload_id=%s where id=%s",
                    (request.mode, uid(request.upload_id) if request.upload_id else None, job),
                )
                return topics.TopicResponse(topic_id=str(job), cached=False)

        return await asyncio.to_thread(run)

    async def persist_upload(
        self,
        document: Document,
        body: bytes | None,
        filename: str | None,
        *,
        demo_consent: bool = False,
    ) -> str:
        # P2 owns private object storage. Linked documents already have canonical provenance.
        if body is not None or not document.source_uri.startswith("https://"):
            raise HTTPException(503, "Cần cấu hình kho lưu trữ riêng trước khi tải tệp.")
        record = prepare_metadata(
            document,
            source_uri=document.source_uri,
            media_type=document.media_type,
            filename=filename,
            upload_id=uuid4(),
        )

        def run() -> str:
            with self.repo.transaction() as conn:
                conn.execute(
                    "insert into uploads(id,source_uri,filename,media_type,byte_size,s"
                    "ha256,page_count,text_ok,pages,demo_consent_at) "
                    "values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        record.id,
                        record.source_uri,
                        record.filename,
                        record.media_type,
                        record.byte_size,
                        record.sha256,
                        record.page_count,
                        record.text_ok,
                        Jsonb([p.model_dump() for p in record.pages]),
                        datetime.now(UTC) if demo_consent else None,
                    ),
                )
            return str(record.id)

        return await asyncio.to_thread(run)


class TutorBackend:
    def __init__(
        self,
        repository: Repository,
        gateway: Gateway,
        confirmation: GraphConfirmation | None = None,
        *,
        demo_uploads_enabled: bool = False,
    ) -> None:
        self.repo, self.gateway = repository, gateway
        self.confirmation = confirmation
        self.demo_uploads_enabled = demo_uploads_enabled

    async def hint(self, request: tutor.HintInput) -> tutor.VerifiedText:
        learner = uid(request.learner_id)

        def prepare() -> tuple[StoredItem, str | None, list[str], str, HintAttempt | None]:
            with self.repo.transaction() as conn:
                if not conn.execute("select id from learners where id=%s", (learner,)).fetchone():
                    raise HTTPException(404, "Không tìm thấy người học.")
                bundle = self.repo.servable(conn, request.item_id)
                if bundle is None:
                    raise HTTPException(503, "Câu hỏi đang chờ kiểm chứng.")
                graph = self.repo.graph(conn, bundle.subject)
                if not graph_confirmed(
                    self.confirmation, request.learner_id, bundle.subject, graph
                ):
                    raise HTTPException(409, "Hãy xác nhận bản đồ kiến thức trước khi xin gợi ý.")
                upload_uris = {
                    source.url for source in bundle.sources if source.version == "uploaded document"
                }
                if upload_uris:
                    if not self.demo_uploads_enabled:
                        raise HTTPException(403, "Tài liệu tải lên chỉ được dùng trong bản demo.")
                    consented = {
                        row[0]
                        for row in conn.execute(
                            "select source_uri from uploads where source_uri=any(%s) "
                            "and demo_consent_at is not null",
                            (list(upload_uris),),
                        )
                    }
                    if not upload_uris <= consented:
                        raise HTTPException(403, "Tài liệu chưa có đồng ý sử dụng cho bản demo.")

                require_model_permission(bundle.sources)
                last = request.last_answer
                if last is None:
                    row = conn.execute(
                        "select answer->>'option_index' from attempts where learner_id=%s "
                        "and item_id=%s order by created_at desc,id desc limit 1",
                        (learner, bundle.db_id),
                    ).fetchone()
                    last = int(row[0]) if row and row[0] is not None else None
                if last is not None and not 0 <= last < len(bundle.item.options):
                    raise HTTPException(422, "Lựa chọn trước đó không hợp lệ.")
                context = bundle.item.options[last].label if last is not None else None
                if last is not None:
                    wrong = bundle.item.options[last].misconception
                    misconception = next(
                        (m.description_vi for m in bundle.item.misconceptions if m.slug == wrong),
                        None,
                    )
                    if misconception:
                        context = f"{context}. Điều cần đối chiếu: {misconception}"
                history = self.repo.hint_history(conn, bundle, learner, request.level)
                key = self.repo.cache_key(
                    bundle, learner, request.level, request.tier, context, history
                )
                cached = conn.execute(
                    "select attempt from p4_hint_cache where cache_key=%s and invalida"
                    "ted_at is null",
                    (key,),
                ).fetchone()
                return (
                    bundle,
                    context,
                    history,
                    key,
                    HintAttempt.model_validate(cached[0]) if cached else None,
                )

        bundle, last, history, key, cached = await asyncio.to_thread(prepare)
        attempt = cached or await generate_hint_attempt(
            bundle.item,
            request.level,
            last,
            bundle.chunks,
            request.tier,
            gateway=self.gateway,
            sources=bundle.sources,
            history=history,
        )
        if attempt is None:
            raise HTTPException(503, "Chưa có gợi ý đã được kiểm chứng.")

        def publish() -> tutor.VerifiedText:
            with self.repo.transaction() as conn:
                if not graph_confirmed(
                    self.confirmation,
                    request.learner_id,
                    bundle.subject,
                    self.repo.graph(conn, bundle.subject),
                ):
                    raise HTTPException(409, "Bản đồ đã đổi; hãy xác nhận lại trước khi xin gợi ý.")
                if not self.repo.save_hint(conn, bundle, learner, key, request.level, attempt):
                    raise HTTPException(409, "Nguồn đã thay đổi; hãy tải lại câu hỏi.")
                current = self.repo.servable(conn, bundle.item.id)
                if current is None:
                    raise HTTPException(503, "Câu hỏi đang chờ kiểm chứng.")
                if self.repo.hint_history(conn, current, learner, request.level) != history:
                    raise HTTPException(409, "Lịch sử gợi ý đã đổi; hãy thử lại.")
                result = release_hint(
                    attempt,
                    current.item,
                    current.chunks,
                    current.sources,
                    level=request.level,
                    last_answer=last,
                    history=history,
                )
            # Commit the failure audit too; withholding a hint must not roll it back.
            if result is None:
                raise HTTPException(503, "Gợi ý chưa vượt qua kiểm chứng.")
            return tutor_text(result)

        return await asyncio.to_thread(publish)

    async def ask(self, request: tutor.AskInput) -> tutor.VerifiedText:
        raise HTTPException(503, "Hỏi đáp truy xuất nguồn chưa được cấu hình.")
