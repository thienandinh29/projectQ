from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize("api_key", ["", "   "])
def test_missing_api_key_refuses_startup_before_database(api_key: str) -> None:
    app = create_app(Settings(api_key=api_key, _env_file=None))
    with (
        patch("app.main.create_pool") as pool,
        pytest.raises(RuntimeError, match="API_KEY is required"),
        TestClient(app),
    ):
        pass
    pool.assert_not_called()


@pytest.mark.parametrize("local_dev", [False, True])
def test_configured_key_is_required_on_routes_even_in_local_dev(local_dev: bool) -> None:
    app = create_app(
        Settings(api_key="test-key", allow_unauthenticated_local_dev=local_dev, _env_file=None)
    )
    with patch("app.main.create_pool", return_value=MagicMock()), TestClient(app) as client:
        assert client.get("/topics/cached").status_code == 401
        assert client.get("/topics/cached", headers={"X-API-Key": "wrong"}).status_code == 401
        assert client.get("/health").status_code == 200


def test_explicit_local_dev_can_start_without_key() -> None:
    app = create_app(Settings(allow_unauthenticated_local_dev=True, _env_file=None))
    with patch("app.main.create_pool", return_value=MagicMock()), TestClient(app) as client:
        assert client.get("/health").status_code == 200
