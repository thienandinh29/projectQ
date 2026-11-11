"""Deterministic answer-disclosure checks on tutor hints (`app.tutor.hints.obvious_leak`)."""

import pytest

from app.content.models import Item, Option
from app.tutor.hints import HintDraft, obvious_leak
from tests.content.fakes import FakeGateway

BASE = FakeGateway().item


def item(correct: str, wrong: list[str]) -> Item:
    """The fixture item with its options replaced (validation already ran on the fixture)."""
    options = [Option(id="opt-a", label=correct, correct=True)] + [
        Option(id=f"opt-{chr(98 + i)}", label=w, correct=False) for i, w in enumerate(wrong)
    ]
    return BASE.model_copy(update={"options": options, "answer_id": "opt-a"})


ITEM = item(
    "vòng lặp while với điều kiện dừng",
    ["vòng lặp for qua range", "câu lệnh if", "hàm print"],
)


def hint(text: str) -> HintDraft:
    return HintDraft(hint_vi=text, chunk_ids=BASE.chunk_ids)


@pytest.mark.parametrize(
    "text",
    [
        "Hãy nghĩ về điều kiện dừng của vòng lặp.",
        "Khi số lần lặp chưa biết trước, ta cần kiểm tra điều gì sau mỗi lần lặp?",
        "Đọc lại mục 5.2 về cách một vòng lặp kết thúc.",
    ],
)
def test_ordinary_hints_pass(text: str) -> None:
    assert not obvious_leak(ITEM, hint(text))


@pytest.mark.parametrize(
    "text",
    [
        "Đáp án là A.",
        "dap an la a",  # without diacritics
        "Hãy chọn opt-a.",
        "Câu trả lời đúng: vòng lặp while với điều kiện dừng.",
        "Cau tra loi: VONG LAP WHILE VOI DIEU KIEN DUNG",  # case and diacritics folded
    ],
)
def test_explicit_disclosure_is_caught(text: str) -> None:
    assert obvious_leak(ITEM, hint(text))


def test_a_light_paraphrase_of_the_answer_is_caught() -> None:
    assert obvious_leak(ITEM, hint("Dùng while, và nhớ đặt điều kiện để vòng lặp dừng."))


def test_short_labels_are_not_judged_by_word_overlap() -> None:
    short = item("while", ["for", "if"])
    assert not obvious_leak(short, hint("Vòng lặp nào kiểm tra điều kiện trước mỗi lần chạy?"))


def test_elimination_across_hints_is_caught() -> None:
    earlier = ["Không phải vòng lặp for qua range.", "Cũng không phải câu lệnh if."]
    last = hint("Và hàm print chỉ in ra màn hình.")
    assert not obvious_leak(ITEM, last)  # alone it names one wrong option
    assert obvious_leak(ITEM, last, history=earlier)  # together every wrong option is excluded
