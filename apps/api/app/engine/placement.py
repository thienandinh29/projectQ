"""Graph-walk placement: find where a learner's knowledge stops, in ~6 questions.

Contract: TEAM.md, "Placement" and "Python interfaces". Pure: the caller (P2's services, P3's route)
loads the learner's answers so far and asks for the next question; nothing is stored here.

How it reasons, per concept: *known*, *unknown* or *undecided*.
  - Correct on X  => X and all its prerequisites are known.
  - Wrong on X    => X and everything that builds on it are unknown.
  - A direct answer beats an inference; between two inferences "unknown" beats "known". An MCQ is
    easier to pass by luck (guess 0.25) than to fail by slip (0.10), so a wrong answer is the
    stronger evidence.

Which question next:
  1. First question: the most advanced concept (deepest in the graph).
  2. While some unknown concept still has undecided prerequisites, only those prerequisites are
     candidates (chase the gap down). Otherwise every undecided concept is a candidate.
  3. Among candidates, the one whose two outcomes split the undecided set most evenly (binary
     search on the DAG); ties go to the deeper concept, then slug order, so runs are repeatable.

It stops when nothing is undecided, when the gap is located (an unknown concept whose
prerequisites are all known), or after `MAX_QUESTIONS` answers.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.engine.graph import UNSEEN_P_KNOWN, Graph
from app.engine.trace import Alternative, DecisionTrace, Evidence, fmt_p, utc_now

MAX_QUESTIONS = 6
# Placement estimates are not mastery: both stay clear of the 0.95 threshold, so Sena only praises
# understanding that later practice (BKT) actually confirms.
KNOWN_P = 0.85
UNKNOWN_P = 0.15
MAX_ALTERNATIVES = 3

Status = Literal["known", "unknown", "undecided"]
DoneReason = Literal["gap_located", "all_known", "budget"]


@dataclass(frozen=True)
class Answer:
    slug: str
    correct: bool
    item_id: str | None = None


def classify(graph: Graph, answers: Sequence[Answer]) -> dict[str, Status]:
    """Status of every concept after `answers` (a later answer to the same concept wins)."""
    direct: dict[str, bool] = {}
    for a in answers:
        if a.slug not in graph:
            raise KeyError(f"answer for unknown concept {a.slug!r}")
        direct[a.slug] = a.correct

    inferred_known: set[str] = set()
    inferred_unknown: set[str] = set()
    for slug, correct in direct.items():
        if correct:
            inferred_known.add(slug)
            inferred_known.update(graph.ancestors(slug))
        else:
            inferred_unknown.add(slug)
            inferred_unknown.update(graph.descendants(slug))

    status: dict[str, Status] = {}
    for n in graph.order:
        if n in direct:
            status[n] = "known" if direct[n] else "unknown"
        elif n in inferred_unknown:
            status[n] = "unknown"
        elif n in inferred_known:
            status[n] = "known"
        else:
            status[n] = "undecided"
    return status


def seed_mastery(graph: Graph, answers: Sequence[Answer]) -> dict[str, float]:
    """Starting `p_known` per concept from placement; P2 stores it, BKT takes over after."""
    values: dict[Status, float] = {
        "known": KNOWN_P,
        "unknown": UNKNOWN_P,
        "undecided": UNSEEN_P_KNOWN,
    }
    return {n: values[s] for n, s in classify(graph, answers).items()}


def gap(graph: Graph, answers: Sequence[Answer]) -> str | None:
    """The most foundational unknown concept, or None when no gap has been found.

    Once the gap is located this is the unknown concept whose prerequisites are all known. If the
    question budget ran out first it is the best estimate: the shallowest unknown concept.
    """
    return _first_unknown(graph, classify(graph, answers))


def _first_unknown(graph: Graph, status: Mapping[str, Status]) -> str | None:
    unknown = [n for n in graph.order if status[n] == "unknown"]
    if not unknown:
        return None
    # Shallowest first; a prerequisite is always shallower than what builds on it.
    return min(unknown, key=lambda n: (graph.depth[n], graph.order.index(n)))


def next_question(
    graph: Graph,
    answers: Sequence[Answer],
    *,
    now: datetime | None = None,
    max_questions: int = MAX_QUESTIONS,
    verify: bool = True,
) -> tuple[str | None, DecisionTrace]:
    """The concept to ask about next, or None when placement is finished; always with a trace.

    `now` only stamps the trace; pass it in tests (defaults to the current UTC time).
    `verify`: when the walk finishes early, spend the leftover budget re-checking inferred-known
    concepts next to the result, so one lucky guess cannot settle the outcome.
    """
    if len(graph) == 0:
        raise ValueError("cannot place a learner on an empty graph")
    now = now or utc_now()
    status = classify(graph, answers)
    undecided = {n for n, s in status.items() if s == "undecided"}
    unknown = [n for n in graph.order if status[n] == "unknown"]
    # Undecided prerequisites of failed concepts: where the gap may still hide.
    chase = {a for u in unknown for a in graph.ancestors(u)} & undecided

    finished = not undecided or bool(unknown and not chase)
    if finished and verify and len(answers) < max_questions:
        checks = _verification_candidates(graph, answers, status)
        if checks:
            return _ask(graph, answers, checks, None, "verify", undecided, now)
    if finished:
        return None, _done(graph, answers, status, "gap_located" if unknown else "all_known", now)
    if len(answers) >= max_questions:
        return None, _done(graph, answers, status, "budget", now)

    if not answers:
        ranked = sorted(undecided, key=lambda n: (-graph.depth[n], -len(graph.ancestors(n)), n))
        return _ask(graph, answers, ranked, None, "start_advanced", undecided, now)

    candidates = chase or undecided
    scores = {c: _split(graph, c, undecided) for c in candidates}
    ranked = sorted(candidates, key=lambda n: (-min(scores[n]), -graph.depth[n], n))
    rule = "chase_gap" if chase else "explore"
    return _ask(graph, answers, ranked, scores, rule, undecided, now)


def _verification_candidates(
    graph: Graph, answers: Sequence[Answer], status: Mapping[str, Status]
) -> list[str]:
    """Inferred-known concepts worth asking directly, most advanced first.

    Next to a located gap these are its prerequisites (a lucky answer elsewhere may have marked them
    known by inference); with no gap, any inferred-known concept.
    """
    asked = {a.slug for a in answers}
    found = _first_unknown(graph, status)
    pool = graph.parents[found] if found else graph.order
    inferred = [n for n in pool if status[n] == "known" and n not in asked]
    return sorted(inferred, key=lambda n: (-graph.depth[n], -len(graph.ancestors(n)), n))


def _split(graph: Graph, slug: str, undecided: set[str]) -> tuple[int, int]:
    """(concepts settled if answered correctly, concepts settled if answered wrongly)."""
    known = ({slug} | set(graph.ancestors(slug))) & undecided
    unknown = ({slug} | set(graph.descendants(slug))) & undecided
    return len(known), len(unknown)


def _ask(
    graph: Graph,
    answers: Sequence[Answer],
    ranked: list[str],
    scores: Mapping[str, tuple[int, int]] | None,
    rule: str,
    undecided: set[str],
    now: datetime,
) -> tuple[str, DecisionTrace]:
    chosen = ranked[0]
    name = graph.name_vi(chosen)
    k, u = scores[chosen] if scores else _split(graph, chosen, undecided)
    outcome = f"đúng → {k} khái niệm được xem là đã biết; sai → {u} khái niệm được xem là chưa biết"
    last = answers[-1] if answers else None

    if rule == "start_advanced":
        why = (
            f"Bắt đầu từ «{name}», khái niệm nâng cao nhất: trả lời đúng thì các kiến thức nền "
            f"coi như đã biết, sai thì ta lần ngược về nền tảng ({outcome})"
        )
    elif rule == "chase_gap":
        why = (
            f"Đã sai một khái niệm nâng cao → kiểm tra kiến thức nền «{name}» "
            f"để biết chỗ hổng nằm ở đâu ({outcome})"
        )
    elif rule == "verify":
        why = (
            f"Kiểm tra lại «{name}» để chắc kết quả không phải do đoán may: "
            "đúng thì giữ nguyên kết luận, sai thì lỗ hổng nằm sâu hơn"
        )
    else:
        why = f"Chưa thấy lỗ hổng nào → kiểm tra «{name}» ở phần chưa rõ ({outcome})"

    alternatives = []
    for other in ranked[1 : 1 + MAX_ALTERNATIVES]:
        ok, ou = scores[other] if scores else _split(graph, other, undecided)
        reason = (
            "Khái niệm kém nâng cao hơn"
            if scores is None
            else f"Thu hẹp kém hơn (đúng → {ok}, sai → {ou} khái niệm)"
        )
        alternatives.append(
            Alternative(concept_slug=other, p_known=UNSEEN_P_KNOWN, why_not_vi=reason)
        )

    trace = DecisionTrace(
        kind="placement_step",
        concept_slug=chosen,
        at=now,
        prior=UNSEEN_P_KNOWN,
        evidence=Evidence(
            item_id=last.item_id if last else None, correct=last.correct if last else None
        ),
        rule=f"placement.{rule}",
        rule_vi=why,
        alternatives=alternatives,
    )
    return chosen, trace


def _done(
    graph: Graph,
    answers: Sequence[Answer],
    status: Mapping[str, Status],
    reason: DoneReason,
    now: datetime,
) -> DecisionTrace:
    found = _first_unknown(graph, status)
    slug = found or (answers[-1].slug if answers else graph.order[-1])
    name = graph.name_vi(slug)
    asked = len(answers)

    if reason == "gap_located":
        why = f"Đã định vị lỗ hổng: «{name}» chưa vững trong khi các kiến thức nền của nó đã vững"
    elif reason == "all_known":
        why = "Các câu hỏi khó đều đúng → kiến thức nền coi như đã vững; chưa thấy lỗ hổng nào"
    elif found:
        why = f"Đã hỏi {asked} câu nên dừng; lỗ hổng ước tính ở «{name}»"
    else:
        why = f"Đã hỏi {asked} câu nên dừng; chưa thấy lỗ hổng nào"

    alternatives: list[Alternative] = []
    if found:
        later = graph.descendants(found)
        for other in graph.order:
            if status[other] == "unknown" and other != found:
                alternatives.append(
                    Alternative(
                        concept_slug=other,
                        p_known=UNKNOWN_P,
                        why_not_vi=(
                            f"Phụ thuộc vào «{name}» nên xử lý sau"
                            if other in later
                            else "Lỗ hổng ở nhánh khác; xử lý sau phần nền tảng hơn"
                        ),
                    )
                )
    prior = UNKNOWN_P if found else (KNOWN_P if reason == "all_known" else UNSEEN_P_KNOWN)
    last = answers[-1] if answers else None
    return DecisionTrace(
        kind="placement_step",
        concept_slug=slug,
        at=now,
        prior=prior,
        evidence=Evidence(
            item_id=last.item_id if last else None, correct=last.correct if last else None
        ),
        rule=f"placement.done.{reason}",
        rule_vi=f"{why} (đã hỏi {asked} câu; p_known ước tính {fmt_p(prior)})",
        alternatives=alternatives[:5],
    )
