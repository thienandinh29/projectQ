"""Short topic requests and private upload persistence; generation belongs to the worker."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.api.topics import TopicInput, TopicResponse
from app.jobs.queue import enqueue
from app.uploads.metadata import UploadMetadata, prepare_metadata
from app.uploads.reader import Document

logger = logging.getLogger(__name__)


class UploadStorage(Protocol):
    async def put(self, upload_id: UUID, body: bytes, media_type: str) -> str: ...
    async def remove(self, upload_id: UUID) -> None: ...


class SupabaseStorage:
    """Server-only object access. The configured bucket must already be private."""

    def __init__(self, url: str, service_role_key: str, bucket: str = "uploads") -> None:
        self.url = url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.headers = {"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"}

    async def put(self, upload_id: UUID, body: bytes, media_type: str) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            bucket = await client.get(
                f"{self.url}/bucket/{quote(self.bucket, safe='')}", headers=self.headers
            )
            bucket.raise_for_status()
            if bucket.json().get("public") is not False:
                raise HTTPException(503, "Kho tài liệu phải được cấu hình riêng tư.")
            response = await client.post(
                f"{self.url}/object/{quote(self.bucket, safe='')}/{upload_id}",
                headers={**self.headers, "Content-Type": media_type, "x-upsert": "false"},
                content=body,
            )
            response.raise_for_status()
        return f"supabase://{self.bucket}/{upload_id}"

    async def remove(self, upload_id: UUID) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                "DELETE",
                f"{self.url}/object/{quote(self.bucket, safe='')}",
                headers=self.headers,
                json={"prefixes": [str(upload_id)]},
            )
            response.raise_for_status()


class TopicsService:
    def __init__(
        self, pool: Callable[[], ConnectionPool], storage: UploadStorage | None = None
    ) -> None:
        self.pool, self.storage = pool, storage

    async def enqueue(self, request: TopicInput) -> TopicResponse:
        return await asyncio.to_thread(self._enqueue, request)

    def _enqueue(self, request: TopicInput) -> TopicResponse:
        upload_id: UUID | None = None
        if request.upload_id:
            try:
                upload_id = UUID(request.upload_id)
            except ValueError:
                raise HTTPException(422, "Mã tài liệu không hợp lệ.") from None
        with self.pool().connection() as conn:
            if upload_id:
                row = conn.execute(
                    "select text_ok from uploads where id=%s", (upload_id,)
                ).fetchone()
                if row is None:
                    raise HTTPException(404, "Không tìm thấy tài liệu đã tải lên.")
                if not row[0]:
                    raise HTTPException(422, "Tài liệu chưa có văn bản đọc được.")
            cached = conn.execute(
                "select id from topic_jobs where goal_vi=%s and tier=%s and mode=%s "
                "and upload_id is not distinct from %s and not fixture and status='ready' "
                "and graph_ready and items_ready order by created_at desc limit 1",
                (request.goal_vi or "", request.tier, request.mode, upload_id),
            ).fetchone()
            if cached:
                return TopicResponse(topic_id=str(cached[0]), cached=True)
            topic_id = enqueue(
                conn,
                request.goal_vi or "",
                request.tier,
                mode=request.mode,
                upload_id=upload_id,
            )
        return TopicResponse(topic_id=str(topic_id), cached=False)

    async def persist_upload(
        self,
        document: Document,
        body: bytes | None,
        filename: str | None,
        *,
        demo_consent: bool = False,
    ) -> str:
        upload_id = uuid4()
        source_uri = document.source_uri
        stored = False
        try:
            if body is not None:
                if self.storage is None:
                    raise HTTPException(503, "Kho tài liệu riêng tư chưa được cấu hình.")
                source_uri = await self.storage.put(upload_id, body, document.media_type)
                stored = True
            metadata = prepare_metadata(
                document,
                source_uri=source_uri,
                media_type=document.media_type,
                body=body,
                filename=filename,
                upload_id=upload_id,
            )
            if demo_consent:
                metadata.demo_consent_at = datetime.now(UTC)
            await asyncio.to_thread(self._save_upload, metadata)
        except BaseException as exc:
            if stored and self.storage is not None:
                try:
                    await asyncio.shield(self.storage.remove(upload_id))
                except Exception:
                    logger.exception("upload cleanup failed", extra={"upload_id": str(upload_id)})
            if isinstance(exc, httpx.HTTPError):
                raise HTTPException(503, "Kho tài liệu tạm thời không truy cập được.") from None
            raise
        return str(upload_id)

    def _save_upload(self, metadata: UploadMetadata) -> None:
        with self.pool().connection() as conn:
            conn.execute(
                "insert into uploads(id,source_uri,filename,media_type,byte_size,sha256,"
                "page_count,text_ok,pages,demo_consent_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    metadata.id,
                    metadata.source_uri,
                    metadata.filename,
                    metadata.media_type,
                    metadata.byte_size,
                    metadata.sha256,
                    metadata.page_count,
                    metadata.text_ok,
                    Jsonb([page.model_dump() for page in metadata.pages]),
                    metadata.demo_consent_at,
                ),
            )


def load_upload(database_url: str, upload_id: str) -> Document | None:
    """Shared by a P4 pipeline adapter to reconstruct exactly the stored pages."""
    import psycopg

    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        row = conn.execute(
            "select id,source_uri,filename,media_type,byte_size,sha256,page_count,text_ok,pages "
            "from uploads where id=%s",
            (UUID(upload_id),),
        ).fetchone()
    return UploadMetadata.model_validate(row).document() if row else None
