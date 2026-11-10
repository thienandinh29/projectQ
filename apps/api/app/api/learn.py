"""P3 learning routes, ready for adapters to P1 engine and P2 persistence.

HTTP responses reuse app.schemas; strict request subclasses preserve existing validation.
Backend protocols describe P3's needs; they do not redefine another lane's API.
"""

from typing import Protocol

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.engine.trace import Alternative as Alternative
from app.engine.trace import Evidence as Evidence
from app.graders.mcq import Grade, Item, grade, learner_item
from app.schemas import (
    AttemptCreate,
    DueCard,
    Edge,
    ExamPlanRequest,
    PlacementRequest,
    PublicItem,
)
from app.schemas import (
    AttemptResult as AttemptResponse,
)
from app.schemas import (
    DecisionTrace as DecisionTrace,
)
from app.schemas import (
    DueReviews as ReviewsResponse,
)
from app.schemas import (
    ExamDay as ExamDay,
)
from app.schemas import (
    ExamPlan as ExamResponse,
)
from app.schemas import (
    GraphNode as GraphNode,
)
from app.schemas import (
    GraphView as GraphResponse,
)
from app.schemas import (
    NextItem as NextResponse,
)
from app.schemas import (
    PlacementStep as PlacementResponse,
)
from app.schemas import (
    Remediation as Remediation,
)

GraphEdge = Edge
ReviewCard = DueCard

__all__ = [
    "Alternative",
    "AttemptInput",
    "AttemptResponse",
    "AttemptUpdate",
    "DecisionTrace",
    "Evidence",
    "ExamDay",
    "ExamInput",
    "ExamResponse",
    "GraphEdge",
    "GraphNode",
    "GraphResponse",
    "Input",
    "LearnerSubject",
    "LearningBackend",
    "NextResponse",
    "NextSelection",
    "Output",
    "PlacementResponse",
    "PlacementSelection",
    "Remediation",
    "ReviewCard",
    "ReviewsResponse",
    "create_router",
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Output(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class LearnerSubject(PlacementRequest):
    model_config = Input.model_config

    learner_id: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=200)


class PlacementSelection(Output):
    item: Item | None
    done: bool
    gap_slug: str | None = None
    trace: DecisionTrace


class NextSelection(Output):
    item: Item
    reason_vi: str


class AttemptInput(AttemptCreate):
    model_config = Input.model_config

    learner_id: str = Field(min_length=1, max_length=200)
    item_id: str = Field(min_length=1, max_length=200)
    # P1: zero-based index in the exact public options order.
    answer: int = Field(ge=0, strict=True)
    hints_used: int = Field(default=0, ge=0, strict=True)


class AttemptUpdate(Output):
    p_known: float = Field(ge=0, le=1)
    mastered: bool
    misconception_vi: str | None = None
    remediation: Remediation | None = None
    traces: list[DecisionTrace]


class ExamInput(ExamPlanRequest, LearnerSubject):
    pass


class LearningBackend(Protocol):
    """Implement these methods in an adapter around actual P1/P2 interfaces.

    apply_attempt must update attempt/mastery/traces/reviews atomically in P2's
    transaction. It must use P1 engine outputs, never an LLM-derived mastery score.
    """

    async def graph(self, learner_id: str, subject: str) -> GraphResponse: ...
    async def placement(self, request: LearnerSubject) -> PlacementSelection: ...
    async def next_item(self, learner_id: str, subject: str) -> NextSelection | None: ...
    async def get_item(self, item_id: str) -> Item | None: ...
    async def apply_attempt(
        self,
        request: AttemptInput,
        item: Item,
        result: Grade,
    ) -> AttemptUpdate | AttemptResponse: ...
    async def reviews_due(self, learner_id: str) -> ReviewsResponse: ...
    async def exam_plan(self, request: ExamInput) -> ExamResponse: ...


def _safe_item(item: Item) -> PublicItem:
    try:
        return PublicItem.model_validate(learner_item(item).model_dump())
    except ValueError:
        raise HTTPException(503, "Câu hỏi đang chờ kiểm chứng.") from None


def create_router(backend: LearningBackend | None = None) -> APIRouter:
    router = APIRouter(tags=["learning"])

    def service() -> LearningBackend:
        if backend is None:
            raise HTTPException(503, "Dịch vụ học tập chưa được cấu hình.")
        return backend

    @router.get("/graph", response_model=GraphResponse)
    async def graph_route(
        learner_id: str = Query(min_length=1, max_length=200),
        subject: str = Query(min_length=1, max_length=200),
    ) -> GraphResponse:
        return await service().graph(learner_id, subject)

    @router.post("/placement/next", response_model=PlacementResponse)
    async def placement_route(request: LearnerSubject) -> PlacementResponse:
        selection = await service().placement(request)
        if selection.done != (selection.item is None):
            raise HTTPException(503, "Kết quả đánh giá đầu vào chưa sẵn sàng.")
        return PlacementResponse(
            item=_safe_item(selection.item) if selection.item else None,
            done=selection.done,
            gap_slug=selection.gap_slug,
            trace=selection.trace,
        )

    @router.get("/next-item", response_model=NextResponse)
    async def next_route(
        learner_id: str = Query(min_length=1, max_length=200),
        subject: str = Query(min_length=1, max_length=200),
    ) -> NextResponse:
        selection = await service().next_item(learner_id, subject)
        if selection is None:
            raise HTTPException(404, "Chưa có câu hỏi phù hợp.")
        return NextResponse(item=_safe_item(selection.item), reason_vi=selection.reason_vi)

    @router.post("/attempts", response_model=AttemptResponse, response_model_exclude_none=True)
    async def attempts_route(request: AttemptInput) -> AttemptResponse:
        adapter = service()
        replay_attempt = getattr(adapter, "replay_attempt", None)
        if replay_attempt is not None:
            cached = await replay_attempt(request)
            if cached is not None:
                return AttemptResponse.model_validate(cached)
        item = await adapter.get_item(request.item_id)
        if item is None:
            raise HTTPException(404, "Không tìm thấy câu hỏi.")
        if item.id != request.item_id:
            raise HTTPException(503, "Dữ liệu câu hỏi không khớp yêu cầu.")
        _safe_item(item)
        try:
            result = grade(item, request.answer)
        except (ValueError, TypeError):
            raise HTTPException(422, "Lựa chọn trả lời không hợp lệ.") from None
        update = await adapter.apply_attempt(request, item, result)
        if isinstance(update, AttemptResponse):
            return update
        values = update.model_dump()
        if result.correct:
            values.update(misconception_vi=None, remediation=None)
        return AttemptResponse(**values, correct=result.correct)

    @router.get("/reviews/due", response_model=ReviewsResponse)
    async def reviews_route(
        learner_id: str = Query(min_length=1, max_length=200),
    ) -> ReviewsResponse:
        return await service().reviews_due(learner_id)

    @router.post("/exam-plan", response_model=ExamResponse)
    async def exam_route(request: ExamInput) -> ExamResponse:
        return await service().exam_plan(request)

    return router
