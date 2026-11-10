"""Offline graph guards; simulated ports do not establish DB/model acceptance."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api.tutor import HintInput
from app.content.backends import LearningBackend, TutorBackend
from app.content.learning import graph_confirmed, graph_revision
from app.content.models import Graph
from app.content.repository import StoredItem
from tests.content.fakes import FakeGateway, topic


@pytest.mark.parametrize("mismatch", ["none", "learner", "topic", "version"])
def test_unconfirmed_or_unrelated_approval_never_unlocks_learning_or_tutor(
    mismatch: str,
) -> None:
    sources, chunks, graph, items = topic()
    learner, subject = str(uuid4()), "python-conditions"
    approved: set[tuple[str, str, str]] = set()
    if mismatch != "none":
        approved_graph = graph.model_copy(deep=True)
        if mismatch == "version":
            approved_graph.concepts[0].description_vi += " changed"
        approved.add(
            (
                str(uuid4()) if mismatch == "learner" else learner,
                "different-topic" if mismatch == "topic" else subject,
                graph_revision(approved_graph),
            )
        )

    def confirmation(who: str, target: str, revision: str) -> bool:
        return (who, target, revision) in approved

    class Connection:
        def execute(self, *args: Any) -> "Connection":
            return self

        def fetchone(self) -> tuple[UUID]:
            return (UUID(learner),)

    class Store:
        @contextmanager
        def transaction(self) -> Iterator[Any]:
            yield Connection()

        def _subject(self, *args: Any) -> UUID:
            return uuid4()

        def graph(self, *args: Any) -> Graph:
            return graph

        def servable(self, *args: Any) -> StoredItem:
            return StoredItem(uuid4(), subject, items[0], chunks, sources, 1)

    store = Store()
    with pytest.raises(HTTPException) as learning_denied:
        LearningBackend(store, confirmation)._state(Connection(), learner, subject)  # type: ignore[arg-type]
    assert learning_denied.value.status_code == 409
    gateway = FakeGateway()
    with pytest.raises(HTTPException) as tutor_denied:
        asyncio.run(
            TutorBackend(store, gateway, confirmation).hint(  # type: ignore[arg-type]
                HintInput(learner_id=learner, item_id=items[0].id, level=1, tier="free")
            )
        )
    assert tutor_denied.value.status_code == 409
    assert gateway.calls == []
    approved.add((learner, subject, graph_revision(graph)))
    assert graph_confirmed(confirmation, learner, subject, graph)
