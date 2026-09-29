from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_health_and_ready_are_explicit_about_database_state() -> None:
    client = TestClient(create_app(Settings.model_construct()))
    health = client.get("/healthz")
    ready = client.get("/readyz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json() == {
        "status": "not_ready",
        "checks": {"application": "ok", "database": "not_configured"},
    }
    assert health.headers["X-Request-ID"]
    assert ready.headers["X-Request-ID"]


def test_error_response_has_request_id() -> None:
    response = TestClient(create_app(Settings.model_construct())).get("/not-a-route")
    assert response.status_code == 404
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
