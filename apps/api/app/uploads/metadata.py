"""Pure upload record conversion matching reserved migration 0007 (P2 persists it)."""

import hashlib
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.uploads.reader import MAX_BYTES, MAX_PAGES, MAX_TEXT, Document, Page


class StoredPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: int = Field(ge=1, le=MAX_PAGES)
    text: str


class UploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    source_uri: str = Field(min_length=1)
    filename: str | None
    media_type: str
    byte_size: int | None = Field(ge=0, le=MAX_BYTES)
    sha256: str | None
    page_count: int = Field(ge=0, le=MAX_PAGES)
    text_ok: bool
    pages: list[StoredPage]
    demo_consent_at: datetime | None = None

    @model_validator(mode="after")
    def consistent(self) -> "UploadMetadata":
        if self.media_type not in {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/html",
            "text/plain",
            "application/xhtml+xml",
        }:
            raise ValueError("Unsupported upload media type")
        if not self.source_uri.strip() or self.page_count != len(self.pages):
            raise ValueError("Canonical source URI and matching page count are required")
        if [page.number for page in self.pages] != list(range(1, self.page_count + 1)):
            raise ValueError("Pages must be contiguous and one-based")
        if sum(len(page.text) for page in self.pages) > MAX_TEXT:
            raise ValueError("Extracted text exceeds the upload limit")
        if self.sha256 is not None and (
            len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256)
        ):
            raise ValueError("Invalid SHA-256")
        return self

    def document(self) -> Document:
        return Document(
            self.source_uri,
            tuple(Page(p.number, p.text) for p in self.pages),
            self.text_ok,
            self.media_type,
        )


def prepare_metadata(
    document: Document,
    *,
    source_uri: str,
    media_type: str,
    filename: str | None = None,
    body: bytes | None = None,
    upload_id: UUID | None = None,
) -> UploadMetadata:
    canonical = replace(document, source_uri=source_uri)
    return UploadMetadata(
        id=upload_id or uuid4(),
        source_uri=canonical.source_uri,
        filename=filename,
        media_type=media_type,
        byte_size=len(body) if body is not None else None,
        sha256=hashlib.sha256(body).hexdigest() if body is not None else None,
        page_count=len(canonical.pages),
        text_ok=canonical.text_ok,
        pages=[StoredPage(number=page.number, text=page.text) for page in canonical.pages],
    )
