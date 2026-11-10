"""Rebuild evaluation fixtures from golden artifacts; never creates human labels or predictions."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def dump(name: str, rows: list[dict[str, object]]) -> None:
    (HERE / name).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def build() -> None:
    golden = []
    for directory in sorted((ROOT / "data/golden").iterdir()):
        if directory.is_dir():
            golden.extend(
                json.loads(line)
                for line in (directory / "items.jsonl").read_text(encoding="utf-8").splitlines()
            )
    cases = [
        {
            "id": f"item-{i + 1:03}",
            "kind": "item",
            "topic": item["id"].rsplit("-", 1)[0],
            "base_item_id": item["id"],
            "payload": item,
        }
        for i, item in enumerate(golden[:44])
    ]
    expected = [
        {
            "id": row["id"],
            "expected_has_error": False,
            "error_type": None,
            "label_origin": "agent_expected_not_human",
        }
        for row in cases
    ]
    faults = [
        "wrong_key",
        "insufficient_evidence",
        "non_supporting_citation",
        "unknown_chunk",
        "multiple_answers",
        "misconception_mismatch",
    ]
    base = next(item for item in golden if item["id"] == "fractions-010")
    for i, fault in enumerate(faults):
        item = copy.deepcopy(base)
        if fault == "wrong_key":
            correct = next(o for o in item["options"] if o["correct"])
            wrong = next(o for o in item["options"] if not o["correct"])
            correct["correct"], wrong["correct"] = False, True
            correct["misconception"], wrong["misconception"] = wrong["misconception"], None
            item["answer_id"] = wrong["id"]
        elif fault == "insufficient_evidence":
            item["prompt_vi"] = "Theo đoạn nguồn, tác giả sinh vào năm nào?"
        elif fault == "non_supporting_citation":
            # Existing chunk, same source, but only explains a/a = 1.
            item["chunk_ids"] = ["40000000-0000-5000-8000-000000000203"]
        elif fault == "unknown_chunk":
            item["chunk_ids"] = ["ffffffff-ffff-5fff-8fff-ffffffffffff"]
        elif fault == "multiple_answers":
            next(o for o in item["options"] if not o["correct"])["label"] = "6/9"
        elif fault == "misconception_mismatch":
            item["misconceptions"][0]["description_vi"] = "Nhầm ribosome với màng tế bào."
        case_id = f"item-{45 + i:03}"
        cases.append(
            {
                "id": case_id,
                "kind": "item",
                "topic": "fractions",
                "base_item_id": base["id"],
                "payload": item,
            }
        )
        expected.append(
            {
                "id": case_id,
                "expected_has_error": True,
                "error_type": fault,
                "label_origin": "agent_expected_not_human",
            }
        )

    hint_cases = []
    for i in range(20):
        item = golden[i % len(golden)]
        level = i % 3 + 1
        hints = {
            1: "Hãy xác định khái niệm đang được hỏi trước khi xem từng lựa chọn.",
            2: "Em có thể viết lại yêu cầu thành một câu hỏi nhỏ hơn, rồi đối chiếu quy tắc không?",
            3: "Hãy đọc mục được trích dẫn và tìm phần mô tả chức năng hoặc định nghĩa liên quan.",
        }
        hint_text, fault = hints[level], None
        if i >= 10:
            fault = [
                "answer_leak",
                "outside_source",
                "invalid_citation",
                "elimination",
                "history_mismatch",
            ][i % 5]
            answer = next(o for o in item["options"] if o["correct"])
            if fault == "answer_leak":
                hint_text = f"Đáp án đúng là {answer['label']}."
            elif fault == "outside_source":
                hint_text = "Mọi tế bào nhân sơ đều chứa ty thể, hãy dùng quy tắc đó."
            elif fault == "elimination":
                excluded = ", ".join(o["label"] for o in item["options"] if not o["correct"])
                hint_text = f"Loại các lựa chọn {excluded}; chỉ còn một lựa chọn."
            elif fault == "history_mismatch":
                hint_text = "Em chưa chọn phương án nào nên không có lỗi cần đối chiếu."
        ids = (
            item["chunk_ids"]
            if fault != "invalid_citation"
            else ["ffffffff-ffff-5fff-8fff-ffffffffffff"]
        )
        case_id = f"hint-{i + 1:03}"
        hint_cases.append(
            {
                "id": case_id,
                "kind": "hint",
                "topic": item["id"].rsplit("-", 1)[0],
                "base_item_id": item["id"],
                "level": level,
                "last_answer": next(o["id"] for o in item["options"] if not o["correct"]),
                "history": [],
                "payload": {"hint_vi": hint_text, "chunk_ids": ids},
            }
        )
        expected.append(
            {
                "id": case_id,
                "expected_has_error": fault is not None,
                "error_type": fault,
                "label_origin": "agent_expected_not_human",
            }
        )
    dump("items.jsonl", cases)
    dump("hints.jsonl", hint_cases)
    dump("expected_labels.jsonl", expected)
    # Template generation is explicit, so rerunning fixtures never overwrites actual annotations.
    labels = [
        {
            "id": row["id"],
            "kind": row["kind"],
            "status": "pending",
            "reviewer": None,
            "reviewed_at": None,
            "has_error": None,
            "tutor_rubric": None,
            "notes": None,
        }
        for row in cases + hint_cases
    ]
    dump("human_labels.template.jsonl", labels)


if __name__ == "__main__":
    build()
