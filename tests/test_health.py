from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_salud_ok():
    response = client.get(f"{settings.api_prefix}/salud")
    assert response.status_code == 200
    data = response.json()
    assert data["estado"] == "ok"
    assert data["servicio"] == settings.app_name
    assert data["umbralCritico"] == settings.umbral_critico


def test_root_ok():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["documentacion"] == "/docs"
