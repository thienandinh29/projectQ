"""Delete demo uploads and their derived topics after stopping the worker.

From apps/api: uv run python -m app.uploads.purge --upload-id UUID
Use --all-demo to purge every upload in the demo database.
"""

import argparse
import asyncio
from uuid import UUID

import psycopg
from fastapi import HTTPException

from app.config import get_settings
from app.db import create_pool
from app.services.topics import SupabaseStorage, TopicsService


async def purge_upload(service: TopicsService, upload_id: UUID) -> bool:
    return await asyncio.to_thread(_purge, service, upload_id)


def _purge(service: TopicsService, upload_id: UUID) -> bool:
    with service.pool().connection() as conn:
        row = conn.execute(
            "select source_uri,filename from uploads where id=%s for update", (upload_id,)
        ).fetchone()
        if row is None:
            return False
        jobs = conn.execute(
            "select id,status from topic_jobs where upload_id=%s for update", (upload_id,)
        ).fetchall()
        if any(status not in {"queued", "ready", "failed"} for _, status in jobs):
            raise HTTPException(409, "Dừng worker và chờ tác vụ hoàn tất trước khi xóa demo.")
        # Only per-job subjects are owned by this upload; curated library data stays intact.
        slugs = [f"topic-{job.hex}" for job, _ in jobs]
        subjects = [
            r[0] for r in conn.execute("select id from subjects where slug=any(%s)", (slugs,))
        ]
        item_ids = [
            r[0]
            for r in conn.execute(
                "select i.id from items i join concepts c on c.id=i.concept_id "
                "where c.subject_id=any(%s)",
                (subjects,),
            )
        ]
        external_ids = [
            r[0]
            for r in conn.execute(
                "select coalesce(external_id,payload->>'id') from items where id=any(%s)",
                (item_ids,),
            )
            if r[0] is not None
        ]
        conn.execute("delete from attempt_replays where item_id=any(%s)", (external_ids,))
        conn.execute("delete from subjects where id=any(%s)", (subjects,))
        # History keeps external IDs after item deletion; remove those retained audits too.
        conn.execute(
            "delete from p4_verification_history where item_id=any(%s) or external_id=any(%s)",
            (item_ids, external_ids),
        )
        conn.execute("delete from llm_calls where topic_id=any(%s)", ([j[0] for j in jobs],))
        conn.execute("delete from topic_jobs where upload_id=%s", (upload_id,))
        # On object-store failure the transaction rolls back, leaving a retryable upload row.
        if row[1] is not None:
            if service.storage is None:
                raise HTTPException(503, "Kho tài liệu riêng tư chưa được cấu hình.")
            asyncio.run(service.storage.remove(upload_id))
        conn.execute("delete from uploads where id=%s", (upload_id,))
        return True


async def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--upload-id", type=UUID)
    selection.add_argument("--all-demo", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    storage = (
        SupabaseStorage(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
            settings.upload_bucket,
        )
        if settings.supabase_url and settings.supabase_service_role_key.get_secret_value()
        else None
    )
    pool = create_pool(settings.database_url)
    try:
        service = TopicsService(lambda: pool, storage)
        with psycopg.connect(settings.database_url) as conn:
            ids = (
                [args.upload_id]
                if args.upload_id
                else [r[0] for r in conn.execute("select id from uploads")]
            )
        for upload_id in ids:
            deleted = await purge_upload(service, upload_id)
            print(f"{upload_id}: {'deleted' if deleted else 'already absent'}")
    finally:
        pool.close()


if __name__ == "__main__":
    asyncio.run(run())
