from pathlib import Path

import pytest
from pydantic import ValidationError

from app.curriculum.course import CourseSpec, FigureNotAllowed, check_figure, load_course
from app.curriculum.figures import ChartFigure, MapFigure

COURSES = Path(__file__).resolve().parents[4] / "data" / "courses"
ALT = "Biểu đồ minh họa cho bài tập."


def base(**over: object) -> dict[str, object]:
    spec: dict[str, object] = {
        "slug": "demo",
        "title_vi": "Demo",
        "title_en": "Demo",
        "source": "authored",
        "modalities": ["mcq", "essay"],
        "figures": ["chart"],
        "rubrics": [
            {"id": "r", "criteria": [{"id": "c", "name_vi": "Tiêu chí", "description": "d"}]}
        ],
        "objectives": [{"id": "o", "concept": "k", "text_vi": "Mục tiêu", "modality": "mcq"}],
    }
    spec.update(over)
    return spec


@pytest.mark.parametrize("path", sorted(COURSES.glob("*.yaml")), ids=lambda p: p.stem)
def test_every_example_course_loads(path: Path) -> None:
    course = load_course(path)
    assert course.slug == path.stem


def test_example_courses_exist() -> None:
    assert {p.stem for p in COURSES.glob("*.yaml")} >= {
        "python-basics",
        "ielts-academic-writing",
        "statistics-intro",
    }


@pytest.mark.parametrize(
    ("objective", "message"),
    [
        ({"modality": "code"}, "not declared"),
        ({"modality": "essay"}, "needs a rubric"),
        ({"modality": "essay", "rubric": "zz"}, "unknown rubric"),
        ({"modality": "mcq", "figures": ["map"]}, "not declared"),
    ],
)
def test_objectives_must_stay_inside_the_course(objective: dict[str, object], message: str) -> None:
    o = {"id": "o", "concept": "k", "text_vi": "Mục tiêu", **objective}
    with pytest.raises(ValidationError, match=message):
        CourseSpec.model_validate(base(objectives=[o]))


def test_code_needs_tests_and_description_needs_a_figure() -> None:
    o = {"id": "o", "concept": "k", "text_vi": "x", "modality": "code"}
    with pytest.raises(ValidationError, match="test cases"):
        CourseSpec.model_validate(base(modalities=["code"], objectives=[o]))
    d = {"id": "o", "concept": "k", "text_vi": "x", "modality": "figure_description", "rubric": "r"}
    with pytest.raises(ValidationError, match="needs a figure kind"):
        CourseSpec.model_validate(base(modalities=["figure_description"], objectives=[d]))


def test_check_figure_allows_only_the_objectives_kinds() -> None:
    course = load_course(COURSES / "ielts-academic-writing.yaml")
    bar = ChartFigure.model_validate(
        {"title": "Sales", "alt_vi": ALT, "chart_type": "bar", "categories": ["a", "b"],
         "series": [{"name": "s", "values": [1, 2]}]}
    )  # fmt: skip
    check_figure(course, "task1-trends", bar)
    town = MapFigure.model_validate(
        {"title": "Town", "alt_vi": ALT, "width": 10, "height": 10,
         "before": [{"id": "a", "label": "a", "type": "park", "x": 0, "y": 0, "w": 1, "h": 1}],
         "after": [{"id": "a", "label": "a", "type": "park", "x": 0, "y": 0, "w": 1, "h": 1}]}
    )  # fmt: skip
    with pytest.raises(FigureNotAllowed, match="allowed: chart"):
        check_figure(course, "task1-trends", town)
    with pytest.raises(FigureNotAllowed, match="allowed: none"):
        check_figure(course, "task2-opinion", bar)
    with pytest.raises(KeyError):
        course.objective("missing")
