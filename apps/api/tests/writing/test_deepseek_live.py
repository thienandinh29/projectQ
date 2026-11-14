"""One real feedback call to DeepSeek (specs/writing/step-2.4.md); costs a few tenths of a cent.

Skipped unless WRITING_LIVE_LLM=1 and DEEPSEEK_API_KEY and DEEPSEEK_FREE_MODEL are set, so CI and
ordinary test runs never call a paid model.
"""

import asyncio
import os

import pytest

from app.llm.providers import default_gateway
from app.writing import feedback

LIVE = os.environ.get("WRITING_LIVE_LLM") == "1" and all(
    os.environ.get(k) for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_FREE_MODEL")
)
pytestmark = pytest.mark.skipif(not LIVE, reason="set WRITING_LIVE_LLM=1 with a DeepSeek key")

ESSAY = (
    "Some people think that plastic bags should be banned. I agree with this idea because "
    "plastic bags pollutes rivers and seas. Many animals dies after eating plastic. However, "
    "shops can give paper bags instead. In conclusion, a ban is a sensible step for the planet."
)


def test_feedback_comes_back_in_the_schema_and_its_quotes_are_checked() -> None:
    out = asyncio.run(
        default_gateway().complete(
            "writing_feedback", "free", feedback.SYSTEM,
            [{"role": "user", "content": feedback.prompt(
                "Some countries ban plastic bags. Do you agree?", ESSAY, {"words": 52})}],
            feedback.FeedbackOut,
        )
    )  # fmt: skip
    assert isinstance(out, feedback.FeedbackOut)
    fb = feedback.verify(ESSAY, out)
    kept = sum(len(p) for p in fb.criteria.values())
    print(
        f"\npoints kept {kept}, dropped {fb.dropped}; quotes {fb.quotes_kept}/{fb.quotes_checked}"
    )
    assert kept >= 1
