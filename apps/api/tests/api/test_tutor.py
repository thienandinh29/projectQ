import pytest

from tests.api.conftest import Harness


@pytest.mark.parametrize("path", ["/ask", "/tutor/hint"])
def test_cited_supported_content_has_only_public_fields(harness: Harness, path: str) -> None:
    body = (
        {"question": "Quang hợp là gì?", "subject": "biology", "tier": "free"}
        if path == "/ask"
        else {"learner_id": "u1", "item_id": "q1", "level": 1, "tier": "pro"}
    )
    response = harness.client.post(path, json=body)
    assert response.status_code == 200
    key = "answer_vi" if path == "/ask" else "hint_vi"
    assert set(response.json()) == {key, "citations"}
    assert response.json()["citations"][0]["url"].startswith("https://")


@pytest.mark.parametrize("path", ["/ask", "/tutor/hint"])
@pytest.mark.parametrize("failure", ["unsupported", "uncited", "blank"])
def test_unverified_content_is_withheld(harness: Harness, path: str, failure: str) -> None:
    if failure == "unsupported":
        harness.backend.text.supported = False
    elif failure == "uncited":
        harness.backend.text.citations = []
    else:
        harness.backend.text.text_vi = "   "
    body = (
        {"question": "Quang hợp?", "subject": "biology", "tier": "free"}
        if path == "/ask"
        else {"learner_id": "u1", "item_id": "q1", "level": 1, "tier": "pro"}
    )
    response = harness.client.post(path, json=body)
    assert response.status_code == 503
    assert "citations" not in response.json()


@pytest.mark.parametrize("level,last_answer", [(0, None), (5, None), (1, "0"), (1, True)])
def test_hint_contract_rejects_invalid_rung_or_answer(
    harness: Harness, level: int, last_answer: object
) -> None:
    response = harness.client.post(
        "/tutor/hint",
        json={
            "learner_id": "u1",
            "item_id": "q1",
            "level": level,
            "last_answer": last_answer,
            "tier": "free",
        },
    )
    assert response.status_code == 422


def test_hint_preserves_pdf_citation_page_and_nullable_section(harness: Harness) -> None:
    from app.api.tutor import Citation

    harness.backend.text.citations = [
        Citation(title="PDF", section=None, url="https://storage.example/signed/file.pdf", page=7)
    ]
    response = harness.client.post(
        "/tutor/hint",
        json={
            "learner_id": "u1",
            "item_id": "q1",
            "level": 4,
            "last_answer": 0,
            "tier": "free",
        },
    )
    assert response.status_code == 200
    assert response.json()["citations"][0]["page"] == 7
    assert response.json()["citations"][0]["section"] is None
