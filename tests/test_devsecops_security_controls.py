"""Pruebas de controles de seguridad en tiempo de ejecución (DevSecOps).

Estas pruebas NO modifican la funcionalidad del negocio: validan que los
controles de seguridad ya implementados (cabeceras OWASP, autenticación JWT
servicio-a-servicio, rate limiting, límite de payload, validación de entrada
y CORS) se comportan como se espera ante entradas maliciosas o inválidas.

Se ejecutan contra la fábrica `build_app` con un Mongo fake, sin tocar
producción ni el contrato de la API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import jwt
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


def _token(secret: str = SECRETO, algorithm: str = "HS256", **overrides) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "iss": "BioGuardApi",
        "aud": "ml-service",
        "tipo": "servicio",
        "iat": int(ahora.timestamp()),
        "exp": int(ahora.timestamp()) + 120,
    }
    payload.update(overrides)
    # PyJWT exige clave None para el algoritmo "none" (simulación de ataque).
    key = None if algorithm == "none" else secret
    return jwt.encode(payload, key, algorithm=algorithm)


@pytest.fixture
def secure_settings() -> Settings:
    return Settings(app_env="production", service_token_secret=SECRETO)


@pytest.fixture
def secure_client(fake_mongo, secure_settings) -> TestClient:
    return TestClient(build_app(mongo=fake_mongo, settings_override=secure_settings))


@pytest.fixture
def auth_headers(secure_settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token_servicio(secure_settings)}"}


# ─────────────────────────────────────────────────────────────────────────────
# Cabeceras de seguridad OWASP (SecurityHeadersMiddleware)
# ─────────────────────────────────────────────────────────────────────────────

ESPERADAS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}


@pytest.mark.parametrize("ruta", ["/health", "/ready", "/docs"])
def test_cabeceras_seguridad_presentes(client, ruta):
    resp = client.get(ruta)
    for cab, valor in ESPERADAS.items():
        assert resp.headers.get(cab) == valor, f"Falta/incorrecta cabecera {cab}"


def test_x_correlation_id_inyectado(client):
    resp = client.get("/health")
    assert "X-Correlation-ID" in resp.headers


def test_server_header_no_fuga_info(client):
    # El middleware enmascara el server real (uvicorn) por uno genérico.
    resp = client.get("/health")
    assert "uvicorn" not in (resp.headers.get("Server") or "").lower()


# ─────────────────────────────────────────────────────────────────────────────
# CORS (sin credenciales + origen no reflejado de forma insegura)
# ─────────────────────────────────────────────────────────────────────────────


def test_cors_no_permite_credenciales(client):
    resp = client.get("/health", headers={"Origin": "https://evil.example"})
    # Con allow_credentials=False no debe aparecer allow-credentials=true.
    assert (resp.headers.get("access-control-allow-credentials") or "").lower() != "true"


# ─────────────────────────────────────────────────────────────────────────────
# Autenticación JWT servicio-a-servicio (producción)
# ─────────────────────────────────────────────────────────────────────────────


def test_produccion_exige_token(secure_client):
    r = secure_client.post("/api/v1/predicciones", json=TELEMETRIA_VALIDA)
    assert r.status_code == 401


def test_produccion_token_valido_201(secure_client, auth_headers):
    r = secure_client.post("/api/v1/predicciones", json=TELEMETRIA_VALIDA, headers=auth_headers)
    assert r.status_code == 201


def test_jwt_algoritmo_none_rechazado(secure_client):
    token = _token(algorithm="none")
    r = secure_client.post(
        "/api/v1/predicciones", json=TELEMETRIA_VALIDA, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


def test_jwt_firma_tamper_rechazado(secure_client):
    token = _token()
    # Alterar la firma (último segmento) sin cambiar el payload.
    head, payload, sig = token.split(".")
    token_malo = f"{head}.{payload}.{sig[:-1]}x"
    r = secure_client.post(
        "/api/v1/predicciones", json=TELEMETRIA_VALIDA, headers={"Authorization": f"Bearer {token_malo}"}
    )
    assert r.status_code == 401


def test_jwt_emisor_incorrecto_rechazado(secure_client):
    token = _token(iss="mallory")
    r = secure_client.post(
        "/api/v1/predicciones", json=TELEMETRIA_VALIDA, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


def test_jwt_sin_exp_rechazado(secure_client):
    payload = {
        "iss": "BioGuardApi",
        "aud": "ml-service",
        "tipo": "servicio",
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    token = jwt.encode(payload, SECRETO, algorithm="HS256")
    r = secure_client.post(
        "/api/v1/predicciones", json=TELEMETRIA_VALIDA, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 401


def test_jwt_tipo_usuario_rechazado(secure_client):
    token = _token(tipo="usuario")
    r = secure_client.post(
        "/api/v1/predicciones", json=TELEMETRIA_VALIDA, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


def test_ruta_interna_exige_auth(secure_client):
    r = secure_client.delete("/api/internal/pacientes/P-001")
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Límite de tamaño de payload (protección DoS en SecurityHeadersMiddleware)
# ─────────────────────────────────────────────────────────────────────────────


def test_payload_excesivo_413(client):
    cuerpo = b" " * (2 * 1024 * 1024 + 256)
    r = client.post(
        "/api/v1/predicciones",
        content=cuerpo,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413


# ─────────────────────────────────────────────────────────────────────────────
# Validación de entrada (rechazo de datos fuera de contrato / peligrosos)
# ─────────────────────────────────────────────────────────────────────────────


def test_campos_desconocidos_rechazados_422(client):
    datos = dict(TELEMETRIA_VALIDA)
    datos["campoMalo"] = "inyeccion"
    r = client.post("/api/v1/predicciones", json=datos)
    assert r.status_code == 422


def test_valores_fuera_de_rango_rechazados_422(client):
    datos = dict(TELEMETRIA_VALIDA)
    datos["frecuenciaCardiaca"] = 9999  # fuera del rango permitido
    r = client.post("/api/v1/predicciones", json=datos)
    assert r.status_code == 422


def test_presion_sistolica_menor_diastolica_rechazada_422(client):
    datos = dict(TELEMETRIA_VALIDA)
    datos["presionSistolica"] = 80
    datos["presionDiastolica"] = 120
    r = client.post("/api/v1/predicciones", json=datos)
    assert r.status_code == 422


def test_tipo_incorrecto_rechazado_422(client):
    datos = dict(TELEMETRIA_VALIDA)
    datos["frecuenciaCardiaca"] = "no-es-numero"
    r = client.post("/api/v1/predicciones", json=datos)
    assert r.status_code == 422


def test_auth_deshabilitado_explicito_permite_sin_token(fake_mongo):
    # Solo con el opt-in explícito de entorno de prueba se permite sin JWT.
    s = Settings(auth_deshabilitado=True)
    c = TestClient(build_app(mongo=fake_mongo, settings_override=s))
    r = c.post("/api/v1/predicciones", json=TELEMETRIA_VALIDA)
    assert r.status_code == 201


def test_auth_requerida_por_defecto(fake_mongo):
    # Por defecto (sin deshabilitar) se exige JWT aunque sea entorno dev.
    s = Settings()  # dev, sin secreto, auth_deshabilitado=False
    c = TestClient(build_app(mongo=fake_mongo, settings_override=s))
    r = c.post("/api/v1/predicciones", json=TELEMETRIA_VALIDA)
    assert r.status_code == 401


def test_docs_deshabilitado_en_produccion(secure_client):
    assert secure_client.get("/docs").status_code == 404
    assert secure_client.get("/openapi.json").status_code == 404
    assert secure_client.get("/redoc").status_code == 404


def test_docs_habilitado_en_desarrollo(client):
    assert client.get("/docs").status_code == 200


def test_cors_default_deny(client):
    r = client.get("/health", headers={"Origin": "https://cualquiera.example"})
    # Por defecto no hay orígenes permitidos: no se refleja CORS abierto.
    assert (r.headers.get("access-control-allow-origin") or "") != "*"


def test_configurar_logging_conecta_formatter():
    from app.core.logging import BankSecurityLogFormatter, configurar_logging

    configurar_logging("INFO")
    root = logging.getLogger()
    assert any(isinstance(h.formatter, BankSecurityLogFormatter) for h in root.handlers)


def test_formatter_enmascara_pii_y_credenciales():
    import logging as _logging

    from app.core.logging import BankSecurityLogFormatter

    fmt = BankSecurityLogFormatter()
    record = _logging.LogRecord(
        "bioguard.test",
        _logging.INFO,
        __file__,
        1,
        "mongodb+srv://user:pass@cluster.net paciente_id=P-001 secret=abc123",
        None,
        None,
    )
    out = fmt.format(record)
    assert "pass@cluster" not in out
    assert "mongodb://[MASKED_URI]" in out
    assert "[MASKED_PATIENT]" in out
    assert "secret=[MASKED_SECRET]" in out
    assert "abc123" not in out


def test_health_no_requiere_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
