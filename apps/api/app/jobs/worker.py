"""Run separately; P4 supplies --pipeline-factory module:function (database_url -> pipeline)."""

import argparse
import asyncio
import importlib
import logging
import time
from collections.abc import Callable
from typing import Any

import psycopg

from app.api.topics import TopicInput
from app.config import get_settings
from app.jobs.queue import append_trail, claim, finish, save_progress
from app.observability import configure_logging
from app.research.pipeline import Progress, TopicPipeline
from app.research.reader import SourceError

logger = logging.getLogger(__name__)


def run_once(
    database_url: str,
    *,
    allow_fixture: bool = False,
    pipeline: TopicPipeline | None = None,
    pipeline_factory: Callable[[str], TopicPipeline] | None = None,
    processor: Callable[[dict[str, Any]], None] | None = None,
) -> bool:
    with psycopg.connect(database_url) as conn:
        job = claim(conn)
    if job is None:
        return False
    if job["fixture"]:
        with psycopg.connect(database_url) as conn:
            finish(conn, job["id"], fixture=allow_fixture)
        return True
    if processor is not None:
        # The claim commits before P3/P4 starts long model work.
        processor(job)
        return True

    async def progress(value: Progress) -> None:
        def persist() -> None:
            with psycopg.connect(database_url) as conn:
                save_progress(conn, job["id"], value)

        await asyncio.to_thread(persist)

    async def trail(event: dict[str, str]) -> None:
        def persist() -> None:
            with psycopg.connect(database_url) as conn:
                append_trail(conn, job["id"], event)

        await asyncio.to_thread(persist)

    async def process() -> None:
        try:
            active_pipeline = pipeline_factory(database_url) if pipeline_factory else pipeline
            if active_pipeline is None:
                raise SourceError("Chưa có bộ sinh và kiểm chứng nội dung từ P4.")
            if not isinstance(active_pipeline, TopicPipeline):
                raise TypeError("pipeline factory must return TopicPipeline")
            await active_pipeline.run(
                TopicInput(
                    goal_vi=job["goal_vi"] or None,
                    upload_id=str(job["upload_id"]) if job["upload_id"] else None,
                    mode=job["mode"],
                    tier=job["tier"],
                ),
                progress,
                trail,
            )
        except Exception as exc:
            # Preserve partial graph/items readiness if the pipeline already published it.
            with psycopg.connect(database_url) as conn:
                conn.execute(
                    "update topic_jobs set status='failed',step_vi=%s,updated_at=now() "
                    "where id=%s and status not in ('ready','failed')",
                    (
                        str(exc)
                        if isinstance(exc, SourceError)
                        else "Không thể xây lộ trình lúc này.",
                        job["id"],
                    ),
                )
            logger.error(
                "topic pipeline failed", extra={"topic_id": str(job["id"]), "tier": job["tier"]}
            )

    asyncio.run(process())
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--pipeline-factory", help="P4 adapter factory: package.module:function")
    parser.add_argument(
        "--pipeline", action="store_true", help="Use configured P4/P3 content ports"
    )
    args = parser.parse_args()
    if args.pipeline and args.pipeline_factory:
        parser.error("choose --pipeline or --pipeline-factory")
    configure_logging()
    settings = get_settings()
    settings.export_worker_environment()
    database_url = settings.database_url
    pipeline_factory = None
    if args.pipeline_factory:
        module, function = args.pipeline_factory.split(":", 1)
        pipeline_factory = getattr(importlib.import_module(module), function)
    if args.pipeline:
        from app.content.gateway import P3Gateway
        from app.content.ports import process_claimed_job
        from app.content.repository import Repository
        from app.db import create_pool
        from app.research.runtime import retrieval_configuration, worker_retriever

        retrieval_subject, retrieval_k = retrieval_configuration()
        with create_pool(database_url) as pool:
            repository = Repository(lambda: pool)
            repository.require_schema()
            gateway = P3Gateway()
            retriever = worker_retriever(pool)

            def process(job: dict[str, Any]) -> None:
                asyncio.run(
                    process_claimed_job(
                        repository,
                        gateway,
                        job,
                        retriever=retriever,
                        retrieval_subject=retrieval_subject,
                        retrieval_k=min(retrieval_k, 6),
                        max_concepts=3,
                    )
                )

            loop(database_url, allow_fixture=args.fixture, processor=process)
        return
    loop(database_url, allow_fixture=args.fixture, pipeline_factory=pipeline_factory)


def loop(
    database_url: str,
    *,
    allow_fixture: bool,
    pipeline_factory: Callable[[str], TopicPipeline] | None = None,
    processor: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    from app.services.writing import load_grammar_step, process_next_essay

    settings = get_settings()
    writing_dir = settings.writing_dir
    # spaCy, ERRANT and the error map load once; a broken error map stops the worker loudly.
    grammar = load_grammar_step(
        writing_dir,
        settings.courses_dir,
        settings.languagetool_url,
        settings.draft_item_learners,
        settings.scorer_url,
    )
    while True:
        try:
            if process_next_essay(database_url, writing_dir, grammar):
                continue  # essays are short: drain them before the next topic job
            if not run_once(
                database_url,
                allow_fixture=allow_fixture,
                pipeline_factory=pipeline_factory,
                processor=processor,
            ):
                time.sleep(1)
        except Exception:
            logger.exception("worker job processing failed")
            time.sleep(2)


if __name__ == "__main__":
    main()
