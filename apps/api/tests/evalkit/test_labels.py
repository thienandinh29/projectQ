"""The labelled-sample format fails loudly on anything that cannot be scored."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.evalkit.labels import Record, RecordSet, classify, load_records


def rec(**kw: Any) -> Record:
    fields: dict[str, Any] = {
        "id": "r1",
        "kind": "item",
        "source": "generated",
        "topic": "python",
        "labels": [{"labeler": "an", "defects": []}],
    }
    return Record.model_validate({**fields, **kw})


def labels(*defect_lists: list[str]) -> list[dict[str, Any]]:
    return [{"labeler": f"p{i}", "defects": d} for i, d in enumerate(defect_lists)]


def test_class_is_good_in_scope_or_out_of_scope() -> None:
    assert rec().klass == "good"
    assert rec(labels=labels(["key_wrong"])).klass == "in_scope"
    assert rec(labels=labels(["vietnamese_error"])).klass == "out_of_scope"
    # one in-scope defect among others makes it in scope
    assert rec(labels=labels(["vietnamese_error", "ambiguous"])).klass == "in_scope"


def test_scope_depends_on_the_kind() -> None:
    assert classify("item", ["ambiguous"]) == "in_scope"
    assert classify("hint", ["wrong"]) == "in_scope"
    assert classify("hint", ["leaks_answer"]) == "out_of_scope"  # a tutor rule, not answerability
    assert classify("item", []) == "good"


def test_a_defect_must_apply_to_the_kind() -> None:
    with pytest.raises(ValidationError, match="does not apply to a hint"):
        rec(kind="hint", labels=labels(["key_wrong"]))
    with pytest.raises(ValidationError, match="does not apply to a item"):
        rec(labels=labels(["leaks_answer"]))


def test_generated_records_need_a_label_from_distinct_people() -> None:
    with pytest.raises(ValidationError, match="at least one label"):
        rec(labels=[])
    twice = [{"labeler": "an", "defects": []}, {"labeler": "an", "defects": []}]
    with pytest.raises(ValidationError, match="twice"):
        rec(labels=twice)


def test_disagreement_on_the_class_must_be_resolved() -> None:
    split = labels([], ["key_wrong"])
    with pytest.raises(ValidationError, match="disagree"):
        rec(labels=split)
    resolved = rec(labels=split, resolved_defects=["key_wrong"])
    assert resolved.klass == "in_scope" and resolved.final_defects == {"key_wrong"}
    # a resolution that nobody needed is a mistake, not a harmless extra
    with pytest.raises(ValidationError, match="agree; resolved_defects is not needed"):
        rec(labels=labels([], []), resolved_defects=[])


def test_same_class_with_different_defects_takes_the_union() -> None:
    both = rec(labels=labels(["key_wrong"], ["not_supported"]))
    assert both.final_defects == {"key_wrong", "not_supported"} and both.klass == "in_scope"


def test_resolution_can_clear_a_record() -> None:
    cleared = rec(labels=labels(["key_wrong"], []), resolved_defects=[])
    assert cleared.klass == "good"


def test_planted_records_are_labelled_by_construction() -> None:
    planted = rec(source="planted", labels=[], planted_defect="key_wrong")
    assert planted.klass == "in_scope" and planted.final_defects == {"key_wrong"}
    with pytest.raises(ValidationError, match="needs planted_defect"):
        rec(source="planted", labels=[])
    with pytest.raises(ValidationError, match="labelled by construction"):
        rec(source="planted", planted_defect="key_wrong")  # still carries a human label
    with pytest.raises(ValidationError, match="only a planted record"):
        rec(planted_defect="key_wrong")


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        rec(extra_field=1)


def test_duplicate_ids_and_empty_sets_are_rejected() -> None:
    one = rec().model_dump()
    with pytest.raises(ValidationError, match="duplicate record ids"):
        RecordSet.model_validate({"records": [one, one]})
    with pytest.raises(ValidationError):
        RecordSet.model_validate({"records": []})


def test_load_records_reads_yaml_with_vietnamese(tmp_path: Path) -> None:
    path = tmp_path / "sample.yaml"
    path.write_text(
        "records:\n"
        "  - id: g-001\n    kind: item\n    source: generated\n    topic: python\n"
        "    payload: {prompt_vi: 'Giá trị của `not True` là gì?'}\n"
        "    chunk_ids: [c1, c2]\n"
        "    labels:\n      - {labeler: an, defects: []}\n"
        "      - {labeler: binh, defects: [key_wrong]}\n"
        "    resolved_defects: [key_wrong]\n"
        "  - id: p-001\n    kind: item\n    source: planted\n    topic: python\n"
        "    planted_defect: key_wrong\n",
        encoding="utf-8",
    )
    records = load_records(path)
    assert [r.klass for r in records] == ["in_scope", "in_scope"]
    assert "Giá trị" in records[0].payload["prompt_vi"]
