"""Model calls for writing: budget first, then the gateway, then one llm_calls row per attempt.

Every attempt is recorded (including invalid and failed replies: they cost money too), with the
learner, the task, tokens and the cost from the configured prices (specs/writing/step-2.4.md).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import psycopg
from pydantic import BaseModel

from app.llm.gateway import Attempt, Gateway
from app.services.budget import Budget, spent_today


class BudgetExceeded(Exception):
    """Today's cost cap or this learner's call limit is reached; the step is skipped."""


@dataclass(frozen=True)
class Prices:
    """US$ per million tokens: the provider's real prices (the defaults are deliberately high)."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, a: Attempt) -> float:
        out = a.output_tokens + a.thoughts_tokens
        return (a.input_tokens * self.input_per_mtok + out * self.output_per_mtok) / 1_000_000


class WritingModel:
    def __init__(
        self,
        gateway: Gateway,
        database_url: str,
        budget: Budget,
        prices: Prices,
        *,
        tier: str = "free",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.gateway = gateway
        self.database_url = database_url
        self.budget = budget
        self.prices = prices
        self.tier = tier
        self.clock = clock
        self.last_model = ""

    def complete[T: BaseModel](
        self, learner: UUID, task: str, system: str, user: str, schema: type[T]
    ) -> T:
        with psycopg.connect(self.database_url) as conn:
            if not spent_today(conn, learner, now=self.clock()).allows(self.budget):
                raise BudgetExceeded
        attempts: list[Attempt] = []
        gateway = Gateway(
            self.gateway.routing,
            self.gateway.adapters,
            observe_attempt=attempts.append,
            task_limits=self.gateway.task_limits,
        )
        try:
            completion = asyncio.run(
                gateway.complete_with_metadata(
                    task, self.tier, system, [{"role": "user", "content": user}], schema
                )
            )
        finally:
            self._record(learner, attempts)
        assert isinstance(completion.value, schema)
        self.last_model = completion.route.model
        return completion.value

    def _record(self, learner: UUID, attempts: list[Attempt]) -> None:
        if not attempts:
            return
        with psycopg.connect(self.database_url) as conn:
            for a in attempts:
                conn.execute(
                    "insert into llm_calls(tier,model,latency_ms,cost_usd,success,learner_id,task,"
                    "input_tokens,output_tokens,created_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        a.tier, a.route.model, round(a.latency_ms), self.prices.cost(a),
                        a.status == "success", learner, a.task, a.input_tokens,
                        a.output_tokens + a.thoughts_tokens, self.clock(),
                    ),
                )  # fmt: skip
