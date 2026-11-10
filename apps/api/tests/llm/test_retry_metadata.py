import httpx
import pytest

from app.llm.providers import http_failure


def test_http_evidence_preserves_quota_and_removes_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sensitive-test-credential")
    response = httpx.Response(
        429,
        headers={"Retry-After": "42", "x-request-id": "req-123"},
        json={
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "message": "key=sensitive-test-credential projects/123",
                "details": [{"violations": [{"quotaId": "RequestsPerDay", "quotaValue": "0"}]}],
            }
        },
    )
    evidence = http_failure(response)
    assert evidence.http_diagnostic["status"] == 429
    assert evidence.http_diagnostic["request_id"] == "req-123"
    assert evidence.http_diagnostic["retry_after_header"] == "42"
    assert "sensitive-test-credential" not in str(evidence.http_diagnostic)
    assert "projects/123" not in str(evidence.http_diagnostic)
    assert evidence.quota_violations[0]["quotaValue"] == "0"


def test_rate_limit_is_not_assumed_to_be_daily_quota() -> None:
    error = http_failure(httpx.Response(429, headers={"Retry-After": "35"}))
    assert error.retry_after == 35
    assert error.retryable
    assert error.failure_kind == "transient"


def test_daily_quota_stops_retries_without_exposing_provider_text() -> None:
    response = httpx.Response(
        429,
        json={
            "error": {
                "message": "private",
                "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProject"}]}],
            }
        },
    )
    error = http_failure(response)
    assert error.failure_kind == "quota"
    assert not error.retryable
    assert str(error) == "http_429"


def test_invalid_credentials_are_not_retried() -> None:
    error = http_failure(httpx.Response(403))
    assert error.failure_kind == "configuration"
    assert not error.retryable


def test_provider_delay_seconds_are_not_milliseconds_or_locale_numbers() -> None:
    for raw, expected in [("64589s", 64589), ("64.589s", 64.589)]:
        error = http_failure(
            httpx.Response(
                429,
                json={
                    "error": {
                        "details": [
                            {"retryDelay": raw},
                            {"violations": [{"quotaId": "RequestsPerDay", "quotaValue": "0"}]},
                        ]
                    }
                },
            )
        )
        assert error.retry_after == expected
        assert error.delay_source == "provider_retry_delay_seconds"
        assert error.quota_violations == [{"quotaId": "RequestsPerDay", "quotaValue": "0"}]
