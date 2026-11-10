from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_db_ok(database_url: str) -> None:
    app = create_app(Settings(database_url=database_url, allow_unauthenticated_local_dev=True))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
