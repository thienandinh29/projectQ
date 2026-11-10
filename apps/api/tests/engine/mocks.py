"""Mock JSON for P5 (web lane): one file per API route shape, built from the contract models.

Run `uv run python -m tests.engine.mocks` from `apps/api` to rewrite `specs/contracts/mocks/`.
`test_mocks.py` fails if the files on disk differ from what this module produces, so the mocks can
never drift from `app/schemas.py`. Traces are real engine output (`update_traced`, `root_cause`,
`review_traced`) with a fixed clock; the placement trace is hand-built until `placement.py` lands.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from app.engine.bkt import DEFAULT_PARAMS, update_traced
from app.engine.graph import Graph
from app.engine.path import next_step
from app.engine.placement import Answer, next_question, seed_mastery
from app.engine.remediation import remediate
from app.engine.srs import make_scheduler, new_card, review_traced
from app.schemas import (
    AskRequest,
    AskResponse,
    AttemptCreate,
    AttemptResult,
    CachedTopic,
    CachedTopics,
    CitationRef,
    Concept,
    DueCard,
    DueReviews,
    Edge,
    ExamDay,
    ExamPlan,
    ExamPlanRequest,
    GraphConfirm,
    GraphConfirmed,
    GraphNode,
    GraphReview,
    GraphView,
    HintRequest,
    HintResponse,
    KnowledgeGraph,
    LearnerCreate,
    LearnerCreated,
    NextItem,
    PlacementRequest,
    PlacementStep,
    PublicItem,
    PublicOption,
    TopicCreate,
    TopicCreated,
    TopicMetrics,
    TopicSource,
    TopicState,
    TrailEvent,
    UploadCreated,
    UploadLink,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MOCKS_DIR = REPO_ROOT / "specs" / "contracts" / "mocks"
NOW = datetime(2026, 11, 7, 9, 30, tzinfo=UTC)
LEARNER = "11111111-1111-4111-8111-111111111111"
SUBJECT = "python-co-ban"
BOOK = "https://allendowney.github.io/ThinkPython"

# Seven concepts, diamond-shaped: variables fan out to two branches that meet at lists.
CONCEPTS: dict[str, str] = {
    "bien": "Biến và phép gán",
    "bieu-thuc": "Biểu thức và toán tử",
    "bieu-thuc-boolean": "Biểu thức boolean",
    "cau-lenh-dieu-kien": "Câu lệnh điều kiện",
    "vong-lap": "Vòng lặp",
    "ham": "Hàm",
    "danh-sach": "Danh sách",
}
EDGES = [
    ("bien", "bieu-thuc"),
    ("bieu-thuc", "bieu-thuc-boolean"),
    ("bieu-thuc-boolean", "cau-lenh-dieu-kien"),
    ("cau-lenh-dieu-kien", "vong-lap"),
    ("bien", "ham"),
    ("vong-lap", "danh-sach"),
    ("ham", "danh-sach"),
]
# After a few placement answers: the learner is solid on variables, shaky on booleans.
MASTERY = {
    "bien": 0.96,
    "bieu-thuc": 0.9,
    "bieu-thuc-boolean": 0.31,
    "cau-lenh-dieu-kien": 0.4,
    "vong-lap": 0.2,
    "ham": 0.6,
    "danh-sach": 0.2,
}
GRAPH = Graph.from_edges(CONCEPTS, EDGES, CONCEPTS)

LOOP_ITEM = PublicItem(
    id="loop-003",
    kind="mcq",
    prompt_vi="Đoạn mã `for i in range(3): print(i)` in ra những giá trị nào?",
    options=[
        PublicOption(label="0, 1, 2"),
        PublicOption(label="1, 2, 3"),
        PublicOption(label="0, 1, 2, 3"),
        PublicOption(label="3"),
    ],
)
BOOL_ITEM = PublicItem(
    id="bool-002",
    kind="mcq",
    prompt_vi="Giá trị của biểu thức `not (3 > 2) or 4 == 4` là gì?",
    options=[
        PublicOption(label="True"),
        PublicOption(label="False"),
        PublicOption(label="Gây lỗi cú pháp"),
        PublicOption(label="None"),
    ],
)
LIST_ITEM = PublicItem(
    id="list-001",
    kind="mcq",
    prompt_vi="Sau `t = [1, 2, 3]` rồi `t.append(4)`, `len(t)` bằng bao nhiêu?",
    options=[
        PublicOption(label="3"),
        PublicOption(label="4"),
        PublicOption(label="5"),
        PublicOption(label="Gây lỗi"),
    ],
)
CITATION = CitationRef(
    title="Think Python (3rd edition)",
    section="Chương 5 — Boolean expressions",
    url=f"{BOOK}/chap05.html#boolean-expressions",
)


# The backend sets this to the sha256 of the generated map; the mock derives it from the demo graph.
GRAPH_REVISION = hashlib.sha256(
    json.dumps([CONCEPTS, EDGES], ensure_ascii=False, sort_keys=True).encode("utf-8")
).hexdigest()
CONCEPTS_EN = {
    "bien": "Variables and assignment",
    "bieu-thuc": "Expressions and operators",
    "bieu-thuc-boolean": "Boolean expressions",
    "cau-lenh-dieu-kien": "Conditional statements",
    "vong-lap": "Loops",
    "ham": "Functions",
    "danh-sach": "Lists",
}


def _graph_view() -> GraphView:
    return GraphView(
        nodes=[
            GraphNode(slug=s, name_vi=n, p_known=MASTERY[s], mastered=MASTERY[s] >= 0.95)
            for s, n in CONCEPTS.items()
        ],
        edges=[Edge(from_=a, to=b) for a, b in EDGES],
    )


def _graph_review() -> GraphReview:
    return GraphReview(
        learner_id=LEARNER,
        subject=SUBJECT,
        graph_revision=GRAPH_REVISION,
        graph=KnowledgeGraph(
            concepts=[
                Concept(slug=s, name_vi=n, name_en=CONCEPTS_EN[s], sources=[f"{BOOK}/chap05.html"])
                for s, n in CONCEPTS.items()
            ],
            edges=[Edge(from_=a, to=b) for a, b in EDGES],
        ),
        confirmed=False,
    )


def _topic_state_ready() -> TopicState:
    trail = [
        TrailEvent(
            at=NOW - timedelta(seconds=50),
            kind="search",
            text_vi="Đang tìm giáo trình mở về «Python cơ bản»…",
        ),
        TrailEvent(
            at=NOW - timedelta(seconds=38),
            kind="read",
            text_vi="Đang đọc Think Python — Chương 5: Điều kiện và đệ quy",
            url=f"{BOOK}/chap05.html",
        ),
        TrailEvent(
            at=NOW - timedelta(seconds=21),
            kind="select",
            text_vi="Chọn 3 nguồn từ 2 nhà xuất bản; thứ tự chương làm cơ sở cho kiến thức nền",
        ),
    ]
    sources = [
        TopicSource(
            title="Think Python (3rd edition)",
            publisher="O'Reilly / Allen Downey",
            url=BOOK,
            license="CC BY-NC-SA 4.0",
        ),
        TopicSource(
            title="Python for Everybody",
            publisher="Charles Severance",
            url="https://www.py4e.com/html3/",
            license="CC BY 4.0",
        ),
        TopicSource(
            title="Python Programming",
            publisher="Wikibooks",
            url="https://en.wikibooks.org/wiki/Python_Programming",
            license="CC BY-SA 4.0",
        ),
    ]
    return TopicState(
        status="ready",
        step_vi="Lộ trình đã sẵn sàng",
        progress=1.0,
        subject_slug=SUBJECT,
        graph_ready=True,
        items_ready=True,
        sources=sources,
        trail=trail,
    )


def _placement_first() -> PlacementStep:
    slug, trace = next_question(GRAPH, [], now=NOW)
    assert slug == "danh-sach"  # the item below is written for this concept
    return PlacementStep(item=LIST_ITEM, done=False, trace=trace)


def _demo_placement_answers() -> list[Answer]:
    """Run the engine against a learner whose real gap is booleans, noiseless (the demo run)."""
    unknown = {"bieu-thuc-boolean", *GRAPH.descendants("bieu-thuc-boolean")}
    answers: list[Answer] = []
    while (slug := next_question(GRAPH, answers, now=NOW)[0]) is not None:
        answers.append(Answer(slug, slug not in unknown))
    return answers


def _placement_done() -> PlacementStep:
    _, trace = next_question(GRAPH, _demo_placement_answers(), now=NOW)
    assert trace.concept_slug == "bieu-thuc-boolean"
    return PlacementStep(item=None, done=True, gap_slug=trace.concept_slug, trace=trace)


def _next_item() -> NextItem:
    """The step after that placement: the gap, not what placement found known."""
    step, _ = next_step(GRAPH, seed_mastery(GRAPH, _demo_placement_answers()), now=NOW)
    assert step.concept_slug == "bieu-thuc-boolean"  # the item below is written for this concept
    return NextItem(item=BOOL_ITEM, reason_vi=step.reason_vi)


def _attempt_wrong() -> AttemptResult:
    mcq = DEFAULT_PARAMS["mcq"]
    p_loop, bkt_trace = update_traced(
        MASTERY["vong-lap"],
        False,
        mcq,
        concept_slug="vong-lap",
        now=NOW,
        item_id="loop-003",
        misconception="range-includes-stop",
    )
    misconception_vi = "Bạn nghĩ `range(3)` gồm cả số 3; thực ra nó dừng trước 3."
    plan, rc_trace = remediate(
        GRAPH,
        MASTERY,
        "vong-lap",
        now=NOW,
        item_id="loop-003",
        misconception="range-includes-stop",
        misconception_vi=misconception_vi,
    )
    return AttemptResult(
        correct=False,
        misconception_vi=misconception_vi,
        p_known=p_loop,
        mastered=False,
        remediation=plan.to_contract(),
        traces=[bkt_trace, rc_trace],
    )


def _attempt_correct() -> AttemptResult:
    mcq = DEFAULT_PARAMS["mcq"]
    p_bool, bkt_trace = update_traced(
        0.93,
        True,
        mcq,
        concept_slug="bieu-thuc-boolean",
        now=NOW,
        item_id="bool-002",
    )
    _, review_trace = review_traced(
        new_card(NOW).state,
        True,
        NOW,
        concept_slug="bieu-thuc-boolean",
        item_id="bool-002",
        scheduler=make_scheduler(fuzz=False),
    )
    return AttemptResult(
        correct=True,
        p_known=p_bool,
        mastered=True,
        traces=[bkt_trace, review_trace],
    )


def mocks() -> dict[str, BaseModel]:
    """File stem -> model. `.request` / `.response` pairs follow the TEAM.md API table."""
    state_ready = _topic_state_ready()
    researching = state_ready.model_copy(
        update={
            "status": "researching",
            "step_vi": "Đang đọc Think Python — Chương 5…",
            "progress": 0.35,
            "subject_slug": None,
            "graph_ready": False,
            "items_ready": False,
            "sources": [],
            "trail": state_ready.trail[:2],
        }
    )
    return {
        "learners.request": LearnerCreate(display_name="Minh"),
        "learners.response": LearnerCreated(learner_id=LEARNER),
        "topics.request": TopicCreate(goal_vi="Tôi muốn học Python", mode="quick", tier="free"),
        "topics.response": TopicCreated(topic_id="topic_7c1e", cached=False),
        "topics-id.researching": researching,
        "topics-id.ready": state_ready,
        "topics-cached.response": CachedTopics(
            topics=[CachedTopic(subject_slug=SUBJECT, name_vi="Python cơ bản")]
        ),
        "uploads.request-link": UploadLink(url="https://example.org/giao-trinh.pdf"),
        "uploads.response": UploadCreated(upload_id="upl_3a9f", pages=42, text_ok=True),
        "graph.response": _graph_view(),
        "graph-review.response": _graph_review(),
        "graph-confirm.request": GraphConfirm(subject=SUBJECT, graph_revision=GRAPH_REVISION),
        "graph-confirm.response": GraphConfirmed(
            learner_id=LEARNER, subject=SUBJECT, graph_revision=GRAPH_REVISION
        ),
        "topic-metrics.response": TopicMetrics(
            topic_id="topic_7c1e",
            elapsed_seconds=142.6,
            cost_usd=None,
            items_generated=12,
            items_verified=9,
            items_dropped=3,
        ),
        "placement-next.request": PlacementRequest(learner_id=LEARNER, subject=SUBJECT),
        "placement-next.question": _placement_first(),
        "placement-next.done": _placement_done(),
        "next-item.response": _next_item(),
        "attempts.request": AttemptCreate(
            learner_id=LEARNER, item_id="loop-003", answer=2, hints_used=0
        ),
        "attempts.wrong": _attempt_wrong(),
        "attempts.correct": _attempt_correct(),
        "tutor-hint.request": HintRequest(
            learner_id=LEARNER, item_id="bool-002", level=2, last_answer=1, tier="pro"
        ),
        "tutor-hint.response": HintResponse(
            hint_vi=(
                "Hãy tính từng vế: `3 > 2` cho giá trị gì? Sau đó `not` đảo giá trị đó thành gì, "
                "và `or` cần ít nhất một vế đúng để cho kết quả True?"
            ),
            citations=[CITATION],
        ),
        "ask.request": AskRequest(
            question="Khi nào dùng `elif` thay vì `if` lồng nhau?", subject=SUBJECT, tier="free"
        ),
        "ask.response": AskResponse(
            answer_vi=(
                "`elif` dùng khi các điều kiện loại trừ nhau và chỉ một nhánh được chạy; "
                "nó gọn hơn `if` lồng nhau."
            ),
            citations=[
                CitationRef(
                    title="Think Python (3rd edition)",
                    section="Chương 5 — Chained conditionals",
                    url=f"{BOOK}/chap05.html#chained-conditionals",
                )
            ],
        ),
        "reviews-due.response": DueReviews(
            cards=[DueCard(concept_slug="bieu-thuc-boolean", due_at=NOW + timedelta(days=3))]
        ),
        "exam-plan.request": ExamPlanRequest(
            learner_id=LEARNER, subject=SUBJECT, exam_date=date(2026, 11, 21)
        ),
        "exam-plan.response": ExamPlan(
            days=[
                ExamDay(
                    date=date(2026, 11, 8),
                    concept_slugs=["bieu-thuc-boolean", "cau-lenh-dieu-kien"],
                    minutes=20,
                ),
                ExamDay(date=date(2026, 11, 9), concept_slugs=["vong-lap"], minutes=20),
            ]
        ),
    }


def render(model: BaseModel) -> str:
    """Stable, human-readable JSON: Vietnamese kept as UTF-8, trailing newline."""
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def write_all(directory: Path = MOCKS_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for stem, model in mocks().items():
        path = directory / f"{stem}.json"
        path.write_text(render(model), encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for p in write_all():
        print(p.relative_to(REPO_ROOT))
