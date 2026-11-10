import json
from datetime import UTC, datetime, timedelta

import pytest
from fsrs import Rating

from app.engine.srs import is_due, make_scheduler, new_card, rating_for, review, review_traced

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
SCHED = make_scheduler(fuzz=False)


def test_rating_mapping() -> None:
    assert rating_for(False) == Rating.Again
    assert rating_for(False, hints_used=2) == Rating.Again
    assert rating_for(True, hints_used=1) == Rating.Hard
    assert rating_for(True) == Rating.Good


def test_negative_hints_rejected() -> None:
    with pytest.raises(ValueError):
        rating_for(True, hints_used=-1)


def test_new_card_is_due_now() -> None:
    card = new_card(NOW)
    assert card.due_at == NOW
    assert is_due(card.due_at, NOW)


def test_state_round_trips_through_json() -> None:
    # The state is stored in a jsonb column, so it must survive json encode/decode.
    first = review(new_card(NOW).state, True, NOW, scheduler=SCHED)
    stored = json.loads(json.dumps(first.state))
    second = review(stored, True, first.due_at, scheduler=SCHED)
    assert second.due_at > first.due_at


def test_first_review_schedules_in_days_not_minutes() -> None:
    result = review(new_card(NOW).state, True, NOW, scheduler=SCHED)
    assert result.due_at - NOW >= timedelta(days=1)


def test_intervals_grow_with_successful_reviews() -> None:
    state, now, gaps = new_card(NOW).state, NOW, []
    for _ in range(4):
        result = review(state, True, now, scheduler=SCHED)
        gaps.append(result.due_at - now)
        state, now = result.state, result.due_at
    assert gaps == sorted(gaps)
    assert gaps[-1] > gaps[0]


def test_failure_shortens_the_next_interval() -> None:
    good = review(new_card(NOW).state, True, NOW, scheduler=SCHED)
    later = good.due_at
    after_good = review(good.state, True, later, scheduler=SCHED)
    after_fail = review(good.state, False, later, scheduler=SCHED)
    assert after_fail.due_at < after_good.due_at


def test_hints_give_shorter_interval_than_clean_answer() -> None:
    start = new_card(NOW).state
    clean = review(start, True, NOW, scheduler=SCHED)
    hinted = review(start, True, NOW, hints_used=1, scheduler=SCHED)
    assert hinted.due_at <= clean.due_at


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValueError):
        new_card(datetime(2026, 10, 22, 9, 0))


def test_non_utc_time_is_normalised() -> None:
    vn = datetime(2026, 10, 22, 16, 0, tzinfo=UTC).astimezone()  # same instant, local tz
    assert new_card(vn).due_at == datetime(2026, 10, 22, 16, 0, tzinfo=UTC)


def test_default_scheduler_replays_identically_without_mutating_state() -> None:
    first = review(new_card(NOW).state, True, NOW)
    second = review(first.state, True, first.due_at)
    before = json.dumps(second.state, sort_keys=True)
    expected = review(second.state, True, second.due_at)
    assert make_scheduler().enable_fuzzing is False
    assert make_scheduler(fuzz=True).enable_fuzzing is True
    for _ in range(20):
        assert review(second.state, True, second.due_at) == expected
        traced, trace = review_traced(second.state, True, second.due_at, concept_slug="water")
        assert traced == expected
        assert trace.at == second.due_at
    assert json.dumps(second.state, sort_keys=True) == before
