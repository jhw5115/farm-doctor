import pytest

pytest.skip("Legacy Phase 1 health endpoints were replaced by /api/v1/health.", allow_module_level=True)

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


def test_liveness_is_available_without_database() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_database_unavailable(monkeypatch) -> None:
    def fail_connection():
        raise OperationalError("SELECT 1", {}, RuntimeError("connection failed"))

    monkeypatch.setattr("app.main.engine.connect", fail_connection)
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "DATABASE_UNAVAILABLE"


def test_readiness_succeeds_when_database_is_available(monkeypatch) -> None:
    connection = MagicMock()
    monkeypatch.setattr("app.main.engine.connect", lambda: connection)

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    connection.__enter__.return_value.execute.assert_called_once()
