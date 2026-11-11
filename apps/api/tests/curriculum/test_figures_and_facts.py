import pytest
from pydantic import TypeAdapter, ValidationError

from app.curriculum.facts import chart_facts, diagram_facts, map_changes, process_steps
from app.curriculum.figures import (
    ChartFigure,
    DiagramFigure,
    Figure,
    FunctionPlotFigure,
    MapFigure,
    ProcessFigure,
    check_expression,
)

ALT = "Biểu đồ minh họa cho bài tập."
FIGURE = TypeAdapter(Figure)


def chart(**over: object) -> ChartFigure:
    data: dict[str, object] = {
        "title": "Internet users",
        "alt_vi": ALT,
        "chart_type": "line",
        "categories": ["2000", "2005", "2010", "2015"],
        "series": [
            {"name": "Vietnam", "values": [1, 10, 30, 45]},
            {"name": "Thailand", "values": [4, 15, 25, 40]},
        ],
        "unit": "%",
    }
    data.update(over)
    return ChartFigure.model_validate(data)


# --- figures ------------------------------------------------------------------------------------


def test_figure_union_dispatches_on_kind() -> None:
    fig = FIGURE.validate_python(
        {"kind": "process", "title": "Recycling", "alt_vi": ALT, "steps": ["collect", "sort"]}
    )
    assert isinstance(fig, ProcessFigure)


def test_chart_series_must_match_categories() -> None:
    with pytest.raises(ValidationError, match="3 values for 4 categories"):
        chart(series=[{"name": "A", "values": [1, 2, 3]}])


def test_chart_rejects_duplicates_and_bad_pies() -> None:
    with pytest.raises(ValidationError, match="unique"):
        chart(categories=["a", "a", "b", "c"])
    with pytest.raises(ValidationError, match="exactly one series"):
        chart(chart_type="pie")
    with pytest.raises(ValidationError, match="negative"):
        chart(
            chart_type="pie",
            categories=["a", "b"],
            series=[{"name": "s", "values": [1, -1]}],
        )


def test_unknown_fields_and_short_alt_text_are_refused() -> None:
    with pytest.raises(ValidationError):
        chart(colour="red")
    with pytest.raises(ValidationError):
        chart(alt_vi="")


def test_map_features_must_fit_the_grid_and_be_unique() -> None:
    feature = {
        "id": "school",
        "label": "school",
        "type": "building",
        "x": 8,
        "y": 0,
        "w": 3,
        "h": 2,
    }
    with pytest.raises(ValidationError, match="outside the grid"):
        MapFigure.model_validate(
            {"title": "Town", "alt_vi": ALT, "width": 10, "height": 10,
             "before": [feature], "after": [feature]}
        )  # fmt: skip


def test_diagram_edges_must_reference_nodes() -> None:
    with pytest.raises(ValidationError, match="missing node"):
        DiagramFigure.model_validate(
            {"title": "Flow", "alt_vi": ALT, "nodes": [{"id": "a", "label": "A"}],
             "edges": [{"source": "a", "target": "b"}]}
        )  # fmt: skip


@pytest.mark.parametrize("expr", ["x^2 - 3*x + 2", "sin(x) + cos(2*x)", "exp(-x^2/2)/sqrt(2*pi)"])
def test_safe_expressions_pass(expr: str) -> None:
    check_expression(expr)


@pytest.mark.parametrize(
    "expr",
    ["__import__('os')", "x.real", "open(x)", "x; y", "(x+1", "x)", "lambda: 1", "x[0]"],
)
def test_unsafe_or_malformed_expressions_are_refused(expr: str) -> None:
    with pytest.raises(ValueError):
        check_expression(expr)


def test_function_plot_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="x_min"):
        FunctionPlotFigure.model_validate(
            {"title": "f", "alt_vi": ALT, "expressions": ["x"], "x_min": 1, "x_max": 1}
        )


# --- facts --------------------------------------------------------------------------------------


def test_chart_facts_are_computed_from_the_data() -> None:
    texts = [f.text for f in chart_facts(chart())]
    assert "Vietnam peaks at 45% in 2015" in texts
    assert "Thailand is lowest at 4% in 2000" in texts
    assert "Vietnam rises from 1% (2000) to 45% (2015)" in texts
    assert "Vietnam's largest rise is 20%, between 2005 and 2010" in texts
    assert "In 2015: Vietnam (45%), Thailand (40%)" in texts


def test_small_overall_change_reads_as_stable() -> None:
    flat = chart(series=[{"name": "A", "values": [50, 70, 30, 51]}], unit="")
    change = next(f for f in chart_facts(flat) if f.kind == "overall_change")
    assert "stays roughly stable" in change.text
    assert change.value == 1


def test_pie_facts_are_shares_in_descending_order() -> None:
    pie = chart(
        chart_type="pie",
        categories=["coal", "gas", "solar"],
        series=[{"name": "energy", "values": [50, 30, 20]}],
    )
    facts = chart_facts(pie)
    assert [f.category for f in facts] == ["coal", "gas", "solar"]
    assert facts[0].text == "coal: 50.0% of the total"


def test_map_changes_match_features_by_id() -> None:
    def f(fid: str, label: str, x: int, w: int = 2, kind: str = "building") -> dict[str, object]:
        return {"id": fid, "label": label, "type": kind, "x": x, "y": 0, "w": w, "h": 2}

    m = MapFigure.model_validate(
        {
            "title": "Village",
            "alt_vi": ALT,
            "width": 20,
            "height": 10,
            "before": [
                f("farm", "farm", 0, kind="farmland"), f("shop", "shop", 4), f("mill", "mill", 8)
            ],
            "after": [
                f("farm", "housing estate", 0), f("shop", "shop", 10), f("mill", "mill", 8, w=4),
                f("park", "park", 14, kind="park"),
            ],
        }
    )  # fmt: skip
    kinds = {(c.kind, c.feature_id) for c in map_changes(m)}
    assert kinds == {
        ("retyped", "farm"),
        ("relabelled", "farm"),
        ("moved", "shop"),
        ("resized", "mill"),
        ("added", "park"),
    }
    assert "The mill was enlarged" in [c.text for c in map_changes(m)]


def test_process_steps_and_cycle() -> None:
    p = ProcessFigure(title="Water", alt_vi=ALT, steps=("evaporation", "rain"), cyclic=True)
    assert process_steps(p)[-1] == "The process then returns to step 1 (evaporation)"


def test_diagram_roots_and_leaves() -> None:
    d = DiagramFigure.model_validate(
        {"title": "If", "alt_vi": ALT,
         "nodes": [{"id": "start", "label": "Start"}, {"id": "check", "label": "n % 2 == 0?"},
                   {"id": "even", "label": "Even"}, {"id": "odd", "label": "Odd"}],
         "edges": [{"source": "start", "target": "check"}, {"source": "check", "target": "even"},
                   {"source": "check", "target": "odd"}]}
    )  # fmt: skip
    facts = diagram_facts(d)
    assert facts.roots == ("start",)
    assert facts.leaves == ("even", "odd")
