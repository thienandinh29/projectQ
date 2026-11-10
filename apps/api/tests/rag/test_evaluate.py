"""Retrieval evaluation: scoring math on synthetic hits, then an end-to-end run on real pgvector."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.rag import evaluate
from app.rag.evaluate import (
    EvalQuestion,
    EvalSet,
    Relevant,
    Report,
    format_report,
    load_eval_set,
    run,
    score_question,
)
from app.rag.notebook import parse_notebook
from app.rag.retrieve import Retriever
from app.schemas import Citation
from tests.rag.fixtures import NOTEBOOK, FakeEmbedder


def hit(uri: str, content: str = "text", score: float = 0.9) -> Citation:
    return Citation(
        chunk_id="c",
        source_title="Book",
        license="CC BY",
        source_uri=uri,
        content=content,
        score=score,
    )


def question(*relevant: Relevant, qid: str = "q1") -> EvalQuestion:
    return EvalQuestion(id=qid, question_vi="Biểu thức boolean là gì?", relevant=list(relevant))


# --- matching ----------------------------------------------------------------------------------


def test_relevant_needs_a_criterion() -> None:
    with pytest.raises(ValidationError, match="source_uri, contains"):
        Relevant()
    with pytest.raises(ValidationError):
        Relevant(contains="ab")  # too short to identify a passage


def test_match_by_uri_is_exact() -> None:
    r = Relevant(source_uri="u/chap05#bool")
    assert r.matches(hit("u/chap05#bool"))
    assert not r.matches(hit("u/chap05#bool-extra"))


def test_match_by_snippet_ignores_case_and_unicode_form() -> None:
    r = Relevant(contains="Biểu thức boolean")
    assert r.matches(hit("u", "…một BIỂU THỨC BOOLEAN là…"))
    assert r.matches(hit("u", "…biểu thức boolean…"))  # decomposed Vietnamese
    assert not r.matches(hit("u", "vòng lặp for"))


def test_both_criteria_must_hold() -> None:
    r = Relevant(source_uri="u/a", contains="modulus")
    assert r.matches(hit("u/a", "the modulus operator"))
    assert not r.matches(hit("u/b", "the modulus operator"))
    assert not r.matches(hit("u/a", "something else"))


# --- scoring one question ----------------------------------------------------------------------


def test_ranks_are_one_based_and_first_match_wins() -> None:
    q = question(Relevant(source_uri="u/b"))
    result = score_question(q, [hit("u/a"), hit("u/b"), hit("u/b")])
    assert result.ranks == (2,) and result.first_rank == 2
    assert not result.hit(1) and result.hit(2) and result.hit(5)


def test_not_retrieved_is_none() -> None:
    result = score_question(question(Relevant(source_uri="u/x")), [hit("u/a")])
    assert result.ranks == (None,) and result.first_rank is None
    assert not result.hit(10) and result.recall(10) == 0


def test_recall_counts_each_relevant_passage() -> None:
    q = question(Relevant(source_uri="u/a"), Relevant(source_uri="u/b"), Relevant(source_uri="u/z"))
    result = score_question(q, [hit("u/a"), hit("u/q"), hit("u/b")])
    assert result.ranks == (1, 3, None) and result.first_rank == 1
    assert result.recall(1) == pytest.approx(1 / 3)
    assert result.recall(3) == pytest.approx(2 / 3)
    assert result.hit(1)  # hit rate only needs one of them


def test_top_hits_are_kept_for_diagnosing_misses() -> None:
    result = score_question(
        question(Relevant(source_uri="u/x")), [hit("u/a", score=0.91234567), hit("u/b", score=0.5)]
    )
    assert result.top == (("u/a", 0.9123), ("u/b", 0.5))


# --- report ------------------------------------------------------------------------------------


def _report() -> Report:
    sets = [
        (question(Relevant(source_uri="u/1"), qid="a"), [hit("u/1")]),  # rank 1
        (question(Relevant(source_uri="u/2"), qid="b"), [hit("u/x"), hit("u/2")]),  # rank 2
        (question(Relevant(source_uri="u/3"), qid="c"), [hit("u/x"), hit("u/y"), hit("u/3")]),  # 3
        (question(Relevant(source_uri="u/4"), qid="d"), [hit("u/x")]),  # missing
    ]
    return Report("python", (1, 3, 5), tuple(score_question(q, h) for q, h in sets))


def test_report_metrics() -> None:
    r = _report()
    assert r.n == 4
    assert r.hit_rate(1) == 0.25 and r.hit_rate(3) == 0.75 and r.hit_rate(5) == 0.75
    assert r.recall(3) == 0.75
    assert r.mrr() == pytest.approx((1 + 1 / 2 + 1 / 3 + 0) / 4)
    assert [m.id for m in r.misses(5)] == ["d"]
    assert [m.id for m in r.misses(1)] == ["b", "c", "d"]


def test_report_to_dict_is_json_serialisable() -> None:
    data = json.loads(json.dumps(_report().to_dict(), ensure_ascii=False))
    assert data["n"] == 4 and data["at_k"]["5"]["hit_rate"] == 0.75
    assert data["misses_at_gate"] == ["d"]


def test_format_report_lists_misses_and_warns_about_small_samples() -> None:
    text = format_report(_report())
    assert "75.0%" in text and "MRR" in text
    assert "Not found in the top 5" in text and "Biểu thức boolean là gì?" in text
    assert "only 4 questions" in text


def test_format_report_shows_how_far_down_a_missed_passage_was_found() -> None:
    # Missed at the k=5 gate but present at rank 7: a reranker could fix this one.
    q = question(Relevant(source_uri="u/9"))
    result = score_question(q, [hit("u/a")] * 6 + [hit("u/9")])
    text = format_report(Report("p", (1, 5, 10), (result,)))
    assert "[found at rank 7]" in text


# --- loading and running -----------------------------------------------------------------------


def test_eval_set_rejects_duplicate_ids_and_unknown_keys() -> None:
    q = {"id": "a", "question_vi": "?", "relevant": [{"source_uri": "u"}]}
    with pytest.raises(ValidationError, match="unique"):
        EvalSet.model_validate({"subject": "s", "questions": [q, q]})
    with pytest.raises(ValidationError):
        EvalSet.model_validate({"subject": "s", "questions": [q], "typo": 1})
    with pytest.raises(ValidationError):
        EvalSet.model_validate({"subject": "s", "questions": []})


def test_load_eval_set_reads_vietnamese_yaml(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text(
        "subject: python\nquestions:\n"
        "  - id: q1\n    question_vi: Khi nào dùng `elif` thay vì `if` lồng nhau?\n"
        "    relevant:\n      - source_uri: https://x/chap05.html#chained-conditionals\n"
        "      - contains: elif\n    note: câu hỏi về điều kiện\n",
        encoding="utf-8",
    )
    s = load_eval_set(path)
    assert s.subject == "python" and "elif" in s.questions[0].question_vi
    assert len(s.questions[0].relevant) == 2


def test_run_searches_once_per_question_at_the_largest_k() -> None:
    calls: list[tuple[str, str, int]] = []

    async def search(query: str, subject: str, k: int) -> list[Citation]:
        calls.append((query, subject, k))
        return [hit("u/1")]

    es = EvalSet(
        subject="s", questions=[question(Relevant(source_uri="u/1"), qid=f"q{i}") for i in range(3)]
    )
    report = asyncio.run(run(es, search, ks=(5, 1, 5, 3)))
    assert report.ks == (1, 3, 5)
    assert [c[2] for c in calls] == [5, 5, 5] and {c[1] for c in calls} == {"s"}
    assert report.hit_rate(1) == 1.0


@pytest.mark.parametrize("ks", [(), (0, 5), (-1,)])
def test_run_rejects_bad_ks(ks: tuple[int, ...]) -> None:
    es = EvalSet(subject="s", questions=[question(Relevant(source_uri="u"))])

    async def search(query: str, subject: str, k: int) -> list[Citation]:
        return []

    with pytest.raises(ValueError):
        asyncio.run(run(es, search, ks=ks))


# --- end to end on real pgvector ---------------------------------------------------------------


def _eval_file(tmp_path: Path, *, impossible: bool) -> Path:
    glossary = next(c for c in parse_notebook(NOTEBOOK, 5) if c.kind == "glossary")
    questions = [
        {
            "id": "glossary",
            "question_vi": glossary.embedding_text,  # the fake embedder matches identical text
            "relevant": [{"source_uri": glossary.source_uri}],
        }
    ]
    if impossible:
        questions.append(
            {
                "id": "nowhere",
                "question_vi": "Câu hỏi không có đoạn nào trả lời",
                "relevant": [{"contains": "this text is in no chunk"}],
            }
        )
    path = tmp_path / "eval.yaml"
    path.write_text(json.dumps({"subject": "python", "questions": questions}), encoding="utf-8")
    return path


def test_end_to_end_on_the_real_retriever(tmp_path: Path, retriever: Retriever) -> None:
    es = load_eval_set(_eval_file(tmp_path, impossible=True))
    report = asyncio.run(run(es, retriever.search))
    by_id = {r.id: r for r in report.results}
    assert by_id["glossary"].first_rank == 1
    assert by_id["nowhere"].first_rank is None
    assert report.hit_rate(5) == 0.5


def _patch_cli(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setattr(
        "app.config.get_settings", lambda: SimpleNamespace(database_url=database_url)
    )
    monkeypatch.setattr("app.rag.embed.make_embedder", lambda *a, **k: FakeEmbedder())


def test_cli_prints_a_report_and_writes_json(
    tmp_path: Path,
    retriever: Retriever,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_cli(monkeypatch, database_url)
    out = tmp_path / "numbers.json"
    code = evaluate.main([str(_eval_file(tmp_path, impossible=False)), "--json", str(out)])
    assert code == 0
    assert "Retrieval on «python»" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))["at_k"]["5"]["hit_rate"] == 1.0


def test_cli_gate_fails_below_the_minimum_hit_rate(
    tmp_path: Path,
    retriever: Retriever,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _patch_cli(monkeypatch, database_url)
    eval_file = str(_eval_file(tmp_path, impossible=True))
    assert evaluate.main([eval_file, "--min-hit-rate", "0.8"]) == 1
    assert "FAIL" in capsys.readouterr().err
    assert evaluate.main([eval_file, "--min-hit-rate", "0.5"]) == 0
