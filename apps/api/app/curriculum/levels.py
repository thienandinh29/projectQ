"""CEFR levels and the indicative IELTS range shown with a level estimate (specs/level-test).

Source: the owner's table of 14 Nov 2026. B1 to C2 follow IELTS's published CEFR alignment; IELTS
publishes no band for A1 and A2, so those are shown as below 4.0, an estimate, never as a precise
band.
"""

from app.curriculum.course import LEVELS, Level

IELTS_RANGE: dict[str, tuple[float, float] | None] = {
    "A1": None,  # below the published alignment
    "A2": None,
    "B1": (4.0, 5.0),
    "B2": (5.5, 6.5),
    "C1": (7.0, 8.0),
}
DISCLAIMER_VI = "ước lượng, không phải điểm IELTS"


def ielts_range_vi(level: Level) -> str:
    """The indicative IELTS range for a CEFR level, in Vietnamese, always marked as an estimate."""
    band = IELTS_RANGE[level]
    if band is None:
        return f"IELTS dưới 4.0 ({DISCLAIMER_VI})"
    return f"IELTS khoảng {band[0]:.1f}–{band[1]:.1f} ({DISCLAIMER_VI})"  # noqa: RUF001


def lower(a: Level, b: Level) -> Level:
    return a if LEVELS.index(a) <= LEVELS.index(b) else b
