"""Against a real LanguageTool (specs/writing/step-2.2.md); skipped without LANGUAGETOOL_URL."""

import os
from pathlib import Path

import pytest

from app.writing.error_map import load_error_map
from app.writing.grammar import analyse_grammar
from app.writing.languagetool import LanguageToolClient

URL = os.environ.get("LANGUAGETOOL_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="LANGUAGETOOL_URL is not set")
MAP = load_error_map(Path(__file__).resolve().parents[4] / "data" / "writing" / "error-map.yaml")


def test_a_subject_verb_error_is_found_typed_and_mapped() -> None:
    import errant
    import spacy

    nlp = spacy.load("en_core_web_sm")
    text = "She go to school every day. The colour is nice."
    issues = analyse_grammar(
        text, LanguageToolClient(URL).matches(text), nlp, errant.load("en", nlp), MAP
    ).issues
    assert [(i.text, i.suggestion, i.errant_type, i.node) for i in issues] == [
        ("go", "goes", "R:VERB:SVA", "present-simple")
    ]
