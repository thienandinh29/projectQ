"""Private persistence for P4's trusted learner/subject/revision callback."""

import re
from uuid import UUID

import psycopg
from fastapi import HTTPException

from app.content.learning import graph_revision
from app.content.models import Graph
from app.services.topic_readiness import require_published_topic


class GraphConfirmations:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def require_schema(self) -> None:
        with psycopg.connect(self.database_url, connect_timeout=3) as conn:
            row = conn.execute("select to_regclass('learner_graph_confirmations')").fetchone()
            if not row or row[0] is None:
                raise RuntimeError("P2 must apply migration 0012_graph_confirmations.sql")

    @staticmethod
    def _current(
        conn: psycopg.Connection, learner: str, subject: str, *, lock: bool = False
    ) -> tuple[UUID, Graph]:
        try:
            learner_id = UUID(learner)
        except ValueError:
            raise HTTPException(422, "Mã người học không hợp lệ.") from None
        suffix = " for update" if lock else ""
        if not conn.execute(
            "select id from learners where id=%s" + suffix, (learner_id,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy người học.")
        require_published_topic(conn, subject)
        row = conn.execute(
            "select id,p4_graph from subjects where slug=%s" + suffix, (subject,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Không tìm thấy chủ đề.")
        if row[1] is None:
            raise HTTPException(503, "Bản đồ kiến thức chưa sẵn sàng.")
        try:
            return row[0], Graph.model_validate(row[1])
        except ValueError:
            raise HTTPException(503, "Bản đồ kiến thức chưa sẵn sàng.") from None

    def snapshot(self, learner: str, subject: str) -> tuple[Graph, str]:
        """P3 must derive the displayed public graph and revision from this same snapshot."""
        with psycopg.connect(self.database_url, connect_timeout=3) as conn:
            _, graph = self._current(conn, learner, subject)
            return graph, graph_revision(graph)

    def confirm(self, learner: str, subject: str, revision: str) -> None:
        """Trusted caller only: authenticate learner and require their explicit acceptance.

        This method must never be called automatically by graph reads or job completion.
        """
        if re.fullmatch(r"[0-9a-f]{64}", revision) is None:
            raise HTTPException(422, "Phiên bản bản đồ không hợp lệ.")
        with psycopg.connect(self.database_url, connect_timeout=3) as conn:
            subject_id, graph = self._current(conn, learner, subject, lock=True)
            if graph_revision(graph) != revision:
                raise HTTPException(409, "Bản đồ đã thay đổi. Hãy xem và xác nhận phiên bản mới.")
            conn.execute(
                "insert into learner_graph_confirmations(learner_id,subject_id,graph_revision) "
                "values(%s,%s,%s) on conflict(learner_id,subject_id) do update set "
                "graph_revision=excluded.graph_revision,confirmed_at=now()",
                (UUID(learner), subject_id, revision),
            )

    def __call__(self, learner: str, subject: str, revision: str) -> bool:
        try:
            learner_id = UUID(learner)
        except ValueError:
            return False
        # P4 already holds a pool connection; borrowing another can exhaust the pool.
        with psycopg.connect(self.database_url, connect_timeout=3) as conn:
            row = conn.execute(
                "select c.graph_revision,s.p4_graph from learner_graph_confirmations c "
                "join subjects s on s.id=c.subject_id "
                "where c.learner_id=%s and s.slug=%s",
                (learner_id, subject),
            ).fetchone()
        if row is None or row[0] != revision or row[1] is None:
            return False
        try:
            return graph_revision(Graph.model_validate(row[1])) == revision
        except ValueError:
            return False
