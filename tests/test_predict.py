from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)

URL = f"{settings.api_prefix}/predicciones"

PAYLOAD_VALIDO = {
    "pacienteId": "P-001",
    "frecuenciaCardiaca": 95,
    "temperatura": 37.2,
    "saturacionOxigeno": 96.0,
    "frecuenciaRespiratoria": 18,
    "presionSistolica": 120,
    "presionDiastolica": 80,
    "glucosa": 105.0,
    "dispositivo": "smartwatch-v1",
}

PAYLOAD_CRITICO = {
    "pacienteId": "P-999",
    "frecuenciaCardiaca": 170,
    "temperatura": 41.0,
    "saturacionOxigeno": 70,
    "frecuenciaRespiratoria": 40,
    "presionSistolica": 190,
    "presionDiastolica": 110,
    "glucosa": 350,
    "dispositivo": "smartwatch-v1",
}


def _payload(**overrides):
    return {**PAYLOAD_VALIDO, **overrides}


def test_prediccion_senal_saludable_probabilidad_baja():
    response = client.post(
        URL,
        json=_payload(
            frecuenciaCardiaca=75,
            temperatura=36.8,
            saturacionOxigeno=98,
            frecuenciaRespiratoria=16,
        ),
    )
    assert response.status_code == 201
    data = response.json()
    assert 0.0 <= data["probabilidad"] < settings.umbral_critico
    assert data["esCritico"] is False
    assert data["umbralCritico"] == settings.umbral_critico
    assert data["modeloId"] == settings.modelo_activo
    assert data["contribuciones"]
    assert data["explicacion"]


def test_prediccion_senal_critica_probabilidad_alta():
    response = client.post(URL, json=PAYLOAD_CRITICO)
    assert response.status_code == 201
    data = response.json()
    assert data["probabilidad"] >= settings.umbral_critico
    assert data["esCritico"] is True
    assert data["nivelRiesgo"] == "CRITICO"


def test_prediccion_responde_al_cambio_de_senales():
    sano = client.post(
        URL,
        json=_payload(
            frecuenciaCardiaca=70,
            temperatura=36.5,
            saturacionOxigeno=98,
            frecuenciaRespiratoria=15,
        ),
    ).json()
    critico = client.post(URL, json=PAYLOAD_CRITICO).json()
    assert sano["probabilidad"] < critico["probabilidad"]
    assert sano["esCritico"] is not critico["esCritico"]


def test_prediccion_severidades_entre_cero_y_uno():
    data = client.post(URL, json=PAYLOAD_CRITICO).json()
    for contribucion in data["contribuciones"]:
        assert 0.0 <= contribucion["severidad"] <= 1.0
        assert contribucion["senal"]
        assert contribucion["valor"] is not None


def test_prediccion_sin_señales_opcionales():
    payload = {
        "paciente_id": "P-003",
        "frecuencia_cardiaca": 82,
        "temperatura": 36.9,
        "saturacion_oxigeno": 97.0,
        "frecuencia_respiratoria": 17,
    }
    response = client.post(URL, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert 0.0 <= data["probabilidad"] <= 1.0
    assert data["pacienteId"] == "P-003"


def test_prediccion_rechaza_valores_fuera_de_rango():
    payload = {**PAYLOAD_VALIDO, "frecuenciaCardiaca": 1000}
    response = client.post(URL, json=payload)
    assert response.status_code == 422


def test_prediccion_rechaza_campos_extra():
    payload = {**PAYLOAD_VALIDO, "campoDesconocido": "x"}
    response = client.post(URL, json=payload)
    assert response.status_code == 422


def test_prediccion_rechaza_presion_inconsistente():
    payload = {**PAYLOAD_VALIDO, "presionSistolica": 80, "presionDiastolica": 120}
    response = client.post(URL, json=payload)
    assert response.status_code == 422


def test_prediccion_rechaza_payload_vacio():
    response = client.post(URL, json={})
    assert response.status_code == 422
