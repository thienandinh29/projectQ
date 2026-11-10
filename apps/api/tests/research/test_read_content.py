import asyncio

import httpx

from app.research.agent import detect_license
from app.research.reader import SafeReader
from app.uploads.reader import read_link


def test_html_reader_indexes_lesson_body_and_keeps_license_evidence_separate() -> None:
    async def public(host: str) -> list[str]:
        return ["93.184.216.34"]

    html = r"""<div class="Headertext">\(\newcommand{\junk}{scaffolding}\)</div>
        <div class="mt-content-container"><h1>Derivative lesson</h1>
        <p>The derivative is the instantaneous rate of change of a function.</p>
        <p>\[f'(x)=2x\]</p></div><footer>CC BY 4.0</footer>"""
    reader = SafeReader(
        resolver=public,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "text/html"}, text=html)
        ),
    )
    document = asyncio.run(read_link("https://books.example/derivatives", reader))
    assert document.text_ok
    assert "newcommand" not in document.pages[0].text
    assert "instantaneous rate of change" in document.pages[0].text
    assert "f'(x)=2x" in document.pages[0].text
    assert "CC BY" not in document.pages[0].text
    assert detect_license(document.license_text) == "CC BY 4.0"
