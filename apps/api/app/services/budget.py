"""The daily model budget (specs/writing/step-2.1.md): how much was spent today, and may a learner
call a model.

Wired into model calls in step 2.4; defined and tested now. "Today" starts at midnight in Vietnam.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg

from app.services.vocabulary import start_of_day


@dataclass(frozen=True)
class Budget:
    cost_cap_usd: float  # the whole service, per day
    calls_per_learner: int  # per learner, per day


@dataclass(frozen=True)
class Spent:
    cost_usd: float  # everyone, today
    learner_calls: int  # this learner, today

    def allows(self, budget: Budget) -> bool:
        return self.cost_usd < budget.cost_cap_usd and self.learner_calls < budget.calls_per_learner


def spent_today(
    conn: psycopg.Connection[Any], learner: UUID | None, *, now: datetime | None = None
) -> Spent:
    since = start_of_day(now or datetime.now(UTC))
    row = conn.execute(
        "select coalesce(sum(cost_usd),0), count(*) filter (where learner_id=%s) "
        "from llm_calls where created_at >= %s",
        (learner, since),
    ).fetchone()
    assert row is not None
    return Spent(float(row[0]), int(row[1]))
