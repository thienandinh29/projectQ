"""Topic enqueue and document uploads, independent of P2's concrete queue/Storage."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import PurePosixPath
from typing import Literal, Protocol

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, HttpUrl, ValidationError, model_validator
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.api.learn import Input, Output
from app.research.reader import SourceError
from app.uploads.reader import MAX_BYTES, Document, read_file, read_link


class TopicInput(Input):
    goal_vi: str | None = Field(default=None, min_length=1, max_length=500)
    upload_id: str | None = Field(default=None, min_length=1, max_length=200)
    mode: Literal["quick", "deep"]
    tier: Literal["free", "pro"]

    @model_validator(mode="after")
    def valid_goal(self) -> "TopicInput":
        if self.goal_vi is None and self.upload_id is None:
            raise ValueError("Cần mục tiêu học tập hoặc tài liệu đã tải lên.")
        if self.mode == "deep" and self.tier == "free":
            raise ValueError("Nghiên cứu sâu yêu cầu gói Pro.")
        return self


class TopicResponse(Output):
    topic_id: str = Field(min_length=1)
    cached: bool


class UploadLink(Input):
    url: HttpUrl


class UploadResponse(Output):
    upload_id: str = Field(min_length=1)
    pages: int = Field(ge=0)
    text_ok: bool


class TopicsBackend(Protocol):
    """P2 adapter: enqueue is short; persist_upload assigns canonical Storage provenance.

    A file Document's source_uri is empty before persistence. The adapter must replace
    it with the actual Storage URI before indexing. A linked document has its final URL.
    Store text_ok=False as an unreadable upload; do not enqueue it for generation.
    """

    async def enqueue(self, request: TopicInput) -> TopicResponse: ...
    async def persist_upload(
        self,
        document: Document,
        body: bytes | None,
        filename: str | None,
        *,
        demo_consent: bool = False,
    ) -> str: ...


ReadLink = Callable[[str], Awaitable[Document]]
MAX_MULTIPART_BYTES = MAX_BYTES + 65_536


async def _limited_body(request: Request, limit: int) -> AsyncGenerator[bytes, None]:
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise MultiPartException("Tài liệu vượt giới hạn dung lượng.")
        yield chunk


async def _upload_file(request: Request) -> tuple[str, bytes]:
    parser = MultiPartParser(
        request.headers,
        _limited_body(request, MAX_MULTIPART_BYTES),
        max_files=1,
        max_fields=0,
        max_part_size=MAX_BYTES,
    )
    try:
        form = await parser.parse()
    except MultiPartException:
        raise HTTPException(413, "Cần đúng một tệp PDF/DOCX, tối đa 20 MB.") from None
    try:
        entries = form.multi_items()
        if (
            len(entries) != 1
            or entries[0][0] != "file"
            or not isinstance(entries[0][1], UploadFile)
        ):
            raise HTTPException(422, "Cần trường file chứa đúng một tệp PDF/DOCX.")
        file = entries[0][1]
        filename = PurePosixPath((file.filename or "").replace("\\", "/")).name
        if len(filename) > 255 or PurePosixPath(filename).suffix.lower() not in {".pdf", ".docx"}:
            raise HTTPException(422, "Chỉ hỗ trợ tệp PDF hoặc DOCX.")
        body = await file.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise HTTPException(413, "Tệp vượt giới hạn 20 MB.")
        return filename, body
    finally:
        await form.close()


def create_router(
    backend: TopicsBackend | None = None,
    *,
    link_reader: ReadLink = read_link,
    demo_uploads_enabled: bool = False,
) -> APIRouter:
    router = APIRouter(tags=["topics"])

    def service() -> TopicsBackend:
        if backend is None:
            raise HTTPException(503, "Dịch vụ chủ đề chưa được cấu hình.")
        return backend

    @router.post("/topics", response_model=TopicResponse)
    async def topics_route(request: TopicInput) -> TopicResponse:
        if request.upload_id and not demo_uploads_enabled:
            raise HTTPException(403, "Tải tài liệu lên chỉ dành cho bản demo.")
        return await service().enqueue(request)

    @router.post(
        "/uploads",
        response_model=UploadResponse,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": UploadLink.model_json_schema()},
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["file"],
                            "properties": {"file": {"type": "string", "format": "binary"}},
                        }
                    },
                },
            },
        },
    )
    async def uploads_route(request: Request) -> UploadResponse:
        if not demo_uploads_enabled:
            raise HTTPException(403, "Tải tài liệu lên chỉ dành cho bản demo.")
        if request.headers.get("x-demo-upload-consent") != "demo-v1":
            raise HTTPException(
                403, "Bạn cần chấp nhận thông báo sử dụng dữ liệu demo trước khi tải lên."
            )
        adapter = service()
        content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        body: bytes | None = None
        filename: str | None = None
        try:
            if content_type == "application/json":
                data = bytearray()
                async for chunk in _limited_body(request, 16_384):
                    data.extend(chunk)
                try:
                    link = UploadLink.model_validate_json(data)
                except ValidationError:
                    raise HTTPException(422, "Đường dẫn tài liệu không hợp lệ.") from None
                document = await link_reader(str(link.url))
            elif content_type == "multipart/form-data":
                filename, body = await _upload_file(request)
                document = await asyncio.to_thread(read_file, filename, body, "")
            else:
                raise HTTPException(415, "Dùng JSON chứa url hoặc multipart chứa file.")
        except MultiPartException:
            raise HTTPException(413, "Yêu cầu vượt giới hạn dung lượng.") from None
        except SourceError as exc:
            raise HTTPException(422, str(exc)) from None
        upload_id = await adapter.persist_upload(document, body, filename, demo_consent=True)
        return UploadResponse(
            upload_id=upload_id, pages=len(document.pages), text_ok=document.text_ok
        )

    return router
