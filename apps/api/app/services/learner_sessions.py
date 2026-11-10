"""Opaque anonymous learner credentials; raw tokens are only sent as HttpOnly cookies."""

import hashlib
import re
import secrets
from uuid import UUID

import psycopg

from app.content.repository import Connection

COOKIE_NAME = "nodetrail_learner"
SESSION_SECONDS = 30 * 24 * 60 * 60


class LearnerSessions:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def require_schema(self) -> None:
        with psycopg.connect(self.database_url, connect_timeout=3) as conn:
            row = conn.execute("select to_regclass('learner_api_sessions')").fetchone()
            if not row or row[0] is None:
                raise RuntimeError("P2 must apply migration 0013_learner_api_sessions.sql")

    @staticmethod
    def issue(conn: Connection, learner: UUID) -> str:
        token = secrets.token_urlsafe(32)
        conn.execute(
            "insert into learner_api_sessions(token_hash,learner_id,expires_at) "
            "values(%s,%s,now()+(%s * interval '1 second'))",
            (hashlib.sha256(token.encode()).hexdigest(), learner, SESSION_SECONDS),
        )
        return token

    def resolve(self, token: str | None) -> UUID | None:
        if token is None or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            return None
        with psycopg.connect(self.database_url, connect_timeout=3) as conn:
            row = conn.execute(
                "select learner_id from learner_api_sessions "
                "where token_hash=%s and expires_at>now()",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
        return UUID(str(row[0])) if row else None
