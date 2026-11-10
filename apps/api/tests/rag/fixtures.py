import hashlib
from collections.abc import Sequence
from typing import Any

from app.rag.embed import EMBEDDING_DIM


def md(text: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict[str, Any]:
    return {"cell_type": "code", "metadata": {}, "source": text}


# Mirrors the real chapter layout, including the cells that must be dropped.
NOTEBOOK: dict[str, Any] = {
    "nbformat": 4,
    "cells": [
        md("You can order print and ebook versions of *Think Python 3e* from Bookshop.org"),
        code("from os.path import basename, exists\n\ndef download(url):\n    pass"),
        md("# Conditionals and Recursion"),
        md("[Run this notebook on Colab](https://colab.research.google.com/x)"),
        md("The main topic of this chapter is the `if` statement."),
        md("## Boolean Expressions\n\nA **boolean expression** is either true or false."),
        code("5 == 5"),
        code("%%expect SyntaxError\nx = = 1"),
        md("## The `else` clause\n\nAn `if` statement can have an `else` clause."),
        md("## Glossary\n\n**modulus operator:** An operator, `%`, that returns the remainder."),
        md("## Exercises"),
        md("### Exercise\n\nWrite a function `is_even`."),
        md("### Exercise\n\nWrite a function `sign`."),
        md("Copyright 2024 Allen B. Downey\n\nCode license: MIT\n\nText license: CC BY-NC-SA"),
    ],
}


class FakeEmbedder:
    """Deterministic vectors from a hash; same text -> same vector, no model download."""

    dim = EMBEDDING_DIM

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for text in texts:
            seed = hashlib.sha256(text.encode()).digest()
            out.append([seed[i % len(seed)] / 255 for i in range(self.dim)])
        return out
