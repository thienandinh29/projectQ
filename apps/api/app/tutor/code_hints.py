"""Deterministic guard for code hints: a hint may point the way, never hand over the solution.

Runs before any code hint is shown (specs/code-sandbox/practice-api.md, behaviour 7), whoever
or whatever wrote it. Conservative: a refused hint costs one hint; a leaked solution costs the
exercise.
"""

import re

MAX_CODE_LINES = 3

_CODE_LINE = re.compile(
    r"^\s*(?:def |return\b|for |while |if |elif |else:|import |from \S+ import |\w+\s*[-+*/%]?=[^=]"
    r"|print\(|\w+\(.*\)\s*$)"
)


def _normalise(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def code_lines(text: str) -> list[str]:
    """Lines that look like Python code, inside or outside fenced blocks."""
    lines = []
    fenced = False
    for raw in text.splitlines():
        if raw.strip().startswith("```"):
            fenced = not fenced
            continue
        if not raw.strip():
            continue
        if fenced or _CODE_LINE.match(raw):
            lines.append(raw)
    return lines


def code_hint_leak(hint: str, function: str, reference: str) -> str | None:
    """Why the hint must be refused, or None when it may be shown."""
    if re.search(rf"\bdef\s+{re.escape(function)}\s*\(", hint):
        return "defines the target function"
    reference_lines = {
        _normalise(line)
        for line in reference.splitlines()
        if line.strip()
        and not line.strip().startswith("def ")
        and len(line.strip()) >= 5  # e.g. 's += x'
    }
    for line in code_lines(hint):
        if _normalise(line) in reference_lines:
            return "contains a line of the reference solution"
    if len(code_lines(hint)) > MAX_CODE_LINES:
        return f"contains more than {MAX_CODE_LINES} lines of code"
    return None
