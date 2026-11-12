import pytest

from app.tutor.code_hints import code_hint_leak, code_lines

REFERENCE = "def total(numbers):\n    s = 0\n    for x in numbers:\n        s += x\n    return s\n"


@pytest.mark.parametrize(
    "hint",
    [
        "Bạn cần một biến để cộng dồn. Mỗi lần lặp, hãy cộng phần tử hiện tại vào biến đó.",
        "Kiểm thử total([]) mong đợi 0: tổng của danh sách rỗng là bao nhiêu?",
        "Thử chạy `total([1, 2])` trong đầu và theo dõi biến sau mỗi vòng lặp.",
        "Ví dụ về vòng lặp:\n```\nfor ch in 'abc':\n    print(ch)\n```",
    ],
)
def test_guiding_hints_pass(hint: str) -> None:
    assert code_hint_leak(hint, "total", REFERENCE) is None


@pytest.mark.parametrize(
    ("hint", "reason"),
    [
        ("Hãy viết:\ndef total(numbers):\n    ...", "defines the target function"),
        ("Gợi ý: dòng này cần có\n    s += x", "reference solution"),
        ("```\nfor x in numbers:\n    s += x\n```", "reference solution"),
        (
            "```\ny = 0\nfor v in items:\n    y = y + v\nprint(y)\n```",
            "more than 3 lines",
        ),
    ],
)
def test_hints_that_hand_over_the_solution_are_refused(hint: str, reason: str) -> None:
    found = code_hint_leak(hint, "total", REFERENCE)
    assert found is not None and reason in found


def test_code_lines_reads_fenced_blocks_and_bare_code() -> None:
    text = "Văn bản.\nx = 1\n```\nfoo\nbar\n```\nKết thúc."
    assert code_lines(text) == ["x = 1", "foo", "bar"]
