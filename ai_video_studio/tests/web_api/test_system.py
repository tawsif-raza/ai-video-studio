from fastapi.testclient import TestClient

from web_api import create_app
from web_api.routers.system import API_VERSION


def test_health_returns_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_api_version():
    client = TestClient(create_app())

    response = client.get("/version")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == API_VERSION
    assert body["service"] == "ai-video-studio-api"
