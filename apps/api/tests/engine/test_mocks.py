"""The mock JSON P5 builds on must match the contracts and never drift from the code."""

import json

import pytest

from app.schemas import PublicItem
from tests.engine.mocks import MOCKS_DIR, mocks, render


@pytest.mark.parametrize("stem", sorted(mocks()))
def test_mock_file_is_current_and_round_trips(stem: str) -> None:
    model = mocks()[stem]
    path = MOCKS_DIR / f"{stem}.json"
    assert path.exists(), "run: uv run python -m tests.engine.mocks"
    assert path.read_text(encoding="utf-8") == render(model), "stale: rerun tests.engine.mocks"
    assert type(model).model_validate(json.loads(path.read_text(encoding="utf-8"))) == model


def test_no_unlisted_files_in_the_mock_folder() -> None:
    on_disk = {p.stem for p in MOCKS_DIR.glob("*.json")}
    assert on_disk == set(mocks())


def test_items_sent_to_the_web_never_hold_the_answer() -> None:
    for stem in ("placement-next.question", "next-item.response"):
        raw = json.loads((MOCKS_DIR / f"{stem}.json").read_text(encoding="utf-8"))
        item = raw["item"]
        assert set(item) == set(PublicItem.model_fields)
        assert all(set(o) == {"label"} for o in item["options"])


def test_graph_mock_edges_use_the_from_key() -> None:
    raw = json.loads((MOCKS_DIR / "graph.response.json").read_text(encoding="utf-8"))
    assert {"from", "to"} == set(raw["edges"][0])


def test_attempt_mocks_tell_the_demo_story() -> None:
    wrong = json.loads((MOCKS_DIR / "attempts.wrong.json").read_text(encoding="utf-8"))
    assert wrong["remediation"]["concept_slug"] == "bieu-thuc-boolean"
    assert [t["kind"] for t in wrong["traces"]] == ["bkt_update", "root_cause"]
    right = json.loads((MOCKS_DIR / "attempts.correct.json").read_text(encoding="utf-8"))
    assert right["mastered"] is True
    assert [t["kind"] for t in right["traces"]] == ["bkt_update", "review"]
