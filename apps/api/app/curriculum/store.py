"""Sync an authored course spec into the database: subject, concepts, prerequisites, code items.

Idempotent: running it again updates names and payloads in place and adds what is new. It never
deletes concepts or items, because attempts and mastery rows may point at them.
"""

from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.curriculum.course import CourseSpec, Objective


def code_item_id(course: CourseSpec, objective: Objective) -> str:
    return f"code:{course.slug}:{objective.id}"


def code_payload(course: CourseSpec, objective: Objective) -> dict[str, Any]:
    assert objective.code is not None
    return {
        "id": code_item_id(course, objective),
        "kind": "code",
        "course": course.slug,
        "objective": objective.id,
        "authored": True,  # written with the course and checked by the grader self-test in CI
        "function": objective.code.function,
        "prompt_vi": objective.code.prompt_vi,
        "starter": objective.code.starter,
        "tests": [t.model_dump() for t in objective.tests],
    }


def sync_course(conn: psycopg.Connection[Any], course: CourseSpec) -> dict[str, UUID]:
    """Upsert the course; returns concept slug -> concept id."""
    if not course.concepts:
        raise ValueError(f"{course.slug}: declare concepts before syncing the course")
    subject = conn.execute(
        "insert into subjects(slug,name_vi,name_en) values (%s,%s,%s) "
        "on conflict(slug) do update set name_vi=excluded.name_vi,name_en=excluded.name_en "
        "returning id",
        (course.slug, course.title_vi, course.title_en),
    ).fetchone()
    assert subject is not None
    ids: dict[str, UUID] = {}
    for c in course.concepts:
        row = conn.execute(
            "insert into concepts(subject_id,slug,name_vi,name_en) values (%s,%s,%s,%s) "
            "on conflict(subject_id,slug) do update "
            "set name_vi=excluded.name_vi,name_en=excluded.name_en returning id",
            (subject[0], c.slug, c.name_vi, c.name_en),
        ).fetchone()
        assert row is not None
        ids[c.slug] = row[0]
    for c in course.concepts:
        for p in c.prerequisites:
            conn.execute(
                "insert into concept_edges(prerequisite_id,concept_id) values (%s,%s) "
                "on conflict do nothing",
                (ids[p], ids[c.slug]),
            )
    for o in course.objectives:
        if o.code is None:
            continue
        payload = code_payload(course, o)
        conn.execute(
            "insert into items(concept_id,kind,prompt,payload,external_id) "
            "values (%s,'code',%s,%s,%s) on conflict(external_id) do update "
            "set concept_id=excluded.concept_id,prompt=excluded.prompt,payload=excluded.payload",
            (ids[o.concept], o.code.prompt_vi, Jsonb(payload), payload["id"]),
        )
    return ids
