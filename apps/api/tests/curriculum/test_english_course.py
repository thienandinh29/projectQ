"""English course skeleton (specs/english-course): levels, the course checker, candidate sources."""

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.curriculum.check import check_course, main, render
from app.curriculum.course import CourseSpec, load_course
from app.sources.candidates import Candidate, load_candidates

DATA = Path(__file__).resolve().parents[4] / "data"
ENGLISH = DATA / "courses" / "english-ielts.yaml"


def course(concepts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "slug": "t", "title_vi": "T", "title_en": "T", "language": "en", "source": "authored",
        "modalities": ["mcq"], "concepts": concepts,
        "objectives": [{"id": f"{c['slug']}-mcq", "concept": c["slug"], "modality": "mcq",
                        "text_vi": "x"} for c in concepts],
    }  # fmt: skip


def concept(slug: str, level: str | None = None, *pre: str) -> dict[str, object]:
    out: dict[str, object] = {
        "slug": slug,
        "name_en": slug,
        "name_vi": slug,
        "prerequisites": list(pre),
    }
    if level:
        out["level"] = level
    return out


def test_the_starter_english_course_is_valid_and_levelled() -> None:
    spec = load_course(ENGLISH)
    assert spec.language == "en" and all(c.level for c in spec.concepts)
    report = check_course(ENGLISH)
    assert report.ok, render(report)
    assert report.order[0].slug in {"be-present", "plural-nouns"}


def test_a_level_is_optional_so_other_courses_are_unchanged() -> None:
    assert load_course(DATA / "courses" / "python-basics.yaml").concepts  # no levels there


def test_a_prerequisite_above_its_dependent_level_is_refused() -> None:
    with pytest.raises(ValidationError, match="higher level"):
        CourseSpec.model_validate(course([concept("hard", "B2"), concept("easy", "A2", "hard")]))


def test_the_checker_reports_every_problem_at_once(tmp_path: Path) -> None:
    bad = course([
        concept("a", "A1", "b"), concept("b", "A1", "a"),  # a cycle
        concept("c", "A1", "missing"),                     # an unknown prerequisite
        concept("d", "A2"), concept("e", "A1", "d"),       # a level inversion
    ])  # fmt: skip
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(bad, allow_unicode=True), encoding="utf-8")
    report = check_course(path)
    text = " | ".join(report.problems)
    assert "cycle" in text and "unknown prerequisite missing" in text and "higher level" in text
    assert main([str(path)]) == 1
    assert main([str(ENGLISH)]) == 0


def test_the_candidates_file_is_valid_and_nothing_is_usable_until_checked() -> None:
    candidates = load_candidates(DATA / "sources" / "english-candidates.yaml")
    assert {"ngsl", "nawl", "tatoeba", "wiktionary"} <= {c.slug for c in candidates.candidates}
    assert candidates.usable() == ()  # nothing verified yet: the owner reads each licence page
    assert any("Cambridge" in e.name for e in candidates.excluded)


BASE = {
    "slug": "x",
    "name": "X",
    "url": "https://example.org/",
    "use": "u",
    "believed_licence": "CC BY 4.0",
}


def test_verified_needs_the_licence_page_and_date_and_never_nd() -> None:
    with pytest.raises(ValidationError, match="checked_on"):
        Candidate.model_validate({**BASE, "status": "verified", "licence": "CC BY 4.0"})
    ok = {"status": "verified", "checked_on": "2026-11-20", "licence_page": "https://example.org/l"}
    with pytest.raises(ValidationError, match="NoDerivatives"):
        Candidate.model_validate({**BASE, **ok, "licence": "CC BY-NC-ND 4.0"})
    nc = Candidate.model_validate({**BASE, **ok, "licence": "CC BY-NC-SA 4.0"})
    assert nc.non_commercial
    assert not Candidate.model_validate({**BASE, **ok, "licence": "CC BY-SA 4.0"}).non_commercial
    with pytest.raises(ValidationError, match="reason"):
        Candidate.model_validate({**BASE, "status": "rejected"})
