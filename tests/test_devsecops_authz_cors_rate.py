"""Pruebas de seguridad en tiempo de ejecución — autorización, CORS, rate
limiting, rutas de error y casos borde de JWT.

NO modifican la funcionalidad de negocio: validan que los controles de
seguridad ya implementados se comportan correctamente ante abusos.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.security import crear_token_servicio
from app.main import build_app

SECRETO = "clave-servicio-devsecops-min-32-caracteres-aaaa"

TELEMETRIA_VALIDA = {
    "pacienteId": "P-001",
    "frecuenciaCardiaca": 80,
    "temperatura": 36.8,
    "saturacionOxigeno": 98,
    "frecuenciaRespiratoria": 16,
}

ORIGEN_PERMITIDO = "https://app.bioguard.example"


@pytest.fixture
def secure_settings() -> Settings:
    return Settings(app_env="production", service_token_secret=SECRETO)


@pytest.fixture
def secure_client(fake_mongo, secure_settings) -> TestClient:
    return TestClient(build_app(mongo=fake_mongo, settings_override=secure_settings))


@pytest.fixture
def auth_headers(secure_settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token_servicio(secure_settings)}"}


@pytest.fixture
def cors_client(fake_mongo) -> TestClient:
    s = Settings(cors_origins=[ORIGEN_PERMITIDO])
    return TestClient(build_app(mongo=fake_mongo, settings_override=s))


# ─────────────────────────────────────────────────────────────────────────────
# Autorización: todas las rutas sensibles exigen JWT en producción
# ─────────────────────────────────────────────────────────────────────────────


def test_v2_requiere_auth(secure_client):
    r = secure_client.post("/api/v2/predicciones", json=TELEMETRIA_VALIDA)
    assert r.status_code == 401


def test_v3_requiere_auth(secure_client):
    # pico glucémico necesita peso/estatura; en producción sin auth → 401 antes de validar.
    r = secure_client.post("/api/v3/predicciones", json=TELEMETRIA_VALIDA)
    assert r.status_code == 401


def test_modelos_activo_requiere_auth(secure_client):
    r = secure_client.get("/api/v2/modelos/activo")
    assert r.status_code == 401


def test_confirmar_evento_requiere_auth(secure_client):
    r = secure_client.post(
        "/api/internal/eventos/confirmar",
        json={"pacienteId": "P-1", "eventoId": "E-1", "confirmado": True},
    )
    assert r.status_code == 401


def test_purgar_paciente_requiere_auth(secure_client):
    r = secure_client.delete("/api/internal/pacientes/P-001")
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# CORS: orígenes restringidos y sin credenciales
# ─────────────────────────────────────────────────────────────────────────────


def test_cors_refleja_origen_permitido(cors_client):
    r = cors_client.get("/health", headers={"Origin": ORIGEN_PERMITIDO})
    assert r.headers.get("access-control-allow-origin") == ORIGEN_PERMITIDO


def test_cors_no_refleja_origen_no_permitido(cors_client):
    r = cors_client.get("/health", headers={"Origin": "https://evil.example"})
    # No debe reflejar un origen no autorizado.
    assert (r.headers.get("access-control-allow-origin") or "") != "https://evil.example"


def test_cors_no_credenciales(cors_client):
    r = cors_client.get("/health", headers={"Origin": ORIGEN_PERMITIDO})
    assert (r.headers.get("access-control-allow-credentials") or "").lower() != "true"


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiting (SlowAPI): presente y activo en producción
# ─────────────────────────────────────────────────────────────────────────────


def test_limiter_registrado_en_app(secure_client):
    assert secure_client.app.state.limiter is not None


def test_rate_limit_no_aplica_en_desarrollo(client):
    # En dev (por defecto) no debe limitar: 101 peticiones -> ninguna 429.
    # Nota: en producción (BIOGUARD_APP_ENV=production al arrancar) los
    # decoradores @limiter.limit se registran y sí aplican el tope.
    codigos = [
        client.post("/api/v1/predicciones", json=TELEMETRIA_VALIDA).status_code
        for _ in range(101)
    ]
    assert 429 not in codigos


def test_limiter_habilitado_en_produccion_por_env(monkeypatch):
    # El limiter se habilita según el entorno por defecto (producción => True).
    # Se valida la lógica de configuración sin alterar el código de la app.
    monkeypatch.setenv("BIOGUARD_APP_ENV", "production")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert get_settings().is_production is True
    finally:
        get_settings.cache_clear()


# ─────────────────────────────────────────────────────────────────────────────
# Cabeceras de seguridad en rutas de error y respuestas anómalas
# ─────────────────────────────────────────────────────────────────────────────


def test_cabeceras_seguridad_en_404(client):
    r = client.get("/ruta-inexistente")
    assert r.status_code == 404
    for cab in ("X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy"):
        assert cab in r.headers


def test_cabeceras_seguridad_en_422(client):
    r = client.post("/api/v1/predicciones", json={"pacienteId": "x"})
    assert r.status_code == 422
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_payload_excesivo_bloqueado_413(client):
    # El middleware de seguridad rechaza payloads > 2MB (protección DoS).
    cuerpo = b" " * (2 * 1024 * 1024 + 256)
    r = client.post(
        "/api/v1/predicciones", content=cuerpo, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 413
    # El mensaje de rechazo no debe filtrar detalles internos.
    assert "ruta" not in r.text.lower() and "traceback" not in r.text.lower()


def test_respuesta_error_sin_stacktrace(client):
    # JSON malformado no debe filtrar trazas internas.
    r = client.post(
        "/api/v1/predicciones",
        content=b"{esto-no-es-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code in (400, 422)
    assert "traceback" not in r.text.lower()
    assert "File \"" not in r.text


# ─────────────────────────────────────────────────────────────────────────────
# /health no filtra configuración sensible
# ─────────────────────────────────────────────────────────────────────────────


def test_health_no_fuga_config_sensible(client):
    r = client.get("/health")
    cuerpo = r.json()
    publicas = {"estado", "servicio", "version", "modeloActivo", "umbralCritico", "enviroment"}
    assert set(cuerpo.keys()).issubset(publicas)
    texto = r.text.lower()
    for fuga in ("mongodb", "password", "secret", "token", "servicetoken"):
        assert fuga not in texto


# ─────────────────────────────────────────────────────────────────────────────
# JWT: casos borde de firma/claims
# ─────────────────────────────────────────────────────────────────────────────


def _jwt(**overrides):
    import jwt
    from datetime import datetime, timezone

    ahora = datetime.now(timezone.utc)
    payload = {
        "iss": "BioGuardApi",
        "aud": "ml-service",
        "tipo": "servicio",
        "iat": int(ahora.timestamp()),
        "exp": int(ahora.timestamp()) + 120,
    }
    payload.update(overrides)
    return jwt.encode(payload, SECRETO, algorithm="HS256")


def test_jwt_sin_audiencia_rechazado(secure_client):
    token = _jwt(aud=None)
    r = secure_client.post(
        "/api/v1/predicciones", json=TELEMETRIA_VALIDA, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


def test_jwt_secreto_distinto_rechazado(secure_client):
    import jwt

    token = jwt.encode(
        {
            "iss": "BioGuardApi",
            "aud": "ml-service",
            "tipo": "servicio",
            "iat": 1,
            "exp": 9_999_999_999,
        },
        "clave-completamente-distinta-1234567890",
        algorithm="HS256",
    )
    r = secure_client.post(
        "/api/v1/predicciones", json=TELEMETRIA_VALIDA, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Validación de entrada (seguridad de contrato)
# ─────────────────────────────────────────────────────────────────────────────


def test_cuerpo_json_nulo_rechazado_422(client):
    r = client.post(
        "/api/v1/predicciones", content=b"null", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422


def test_campo_muy_largo_rechazado_422(client):
    datos = dict(TELEMETRIA_VALIDA)
    datos["pacienteId"] = "P-" + "x" * 100  # supera max_length=64
    r = client.post("/api/v1/predicciones", json=datos)
    assert r.status_code == 422


def test_glucosa_fuera_de_rango_rechazada_422(client):
    datos = dict(TELEMETRIA_VALIDA)
    datos["glucosa"] = 9999.0  # fuera del rango permitido
    r = client.post("/api/v1/predicciones", json=datos)
    assert r.status_code == 422
