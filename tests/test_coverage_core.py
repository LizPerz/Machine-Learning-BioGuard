"""Cobertura de módulos de soporte que la suite principal no ejercitaba:
logging PII, predictor base, cliente Mongo, worker de sync/retrain, lifespan y
rutas de salud en fallo/éxito con Mongo."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.logging import BankSecurityLogFormatter
from app.db.mongo import Mongo
from app.main import _crear_indices, lifespan
from app.schemas.prediccion import NivelRiesgo
from app.services.base import PredictorBase, _nivel_riesgo
from app.services.predictor import PredictorService
from app.worker.retrain import run_retrain
from app.worker.sync import _cambios, _procesar_paciente
from tests.conftest import sembrar_paciente


def test_nivel_riesgo_ramas():
    assert _nivel_riesgo(0.9, 0.85) is NivelRiesgo.CRITICO
    assert _nivel_riesgo(0.7, 0.85) is NivelRiesgo.ALTO
    assert _nivel_riesgo(0.5, 0.85) is NivelRiesgo.MODERADO
    assert _nivel_riesgo(0.1, 0.85) is NivelRiesgo.BAJO


def test_predictor_base_abstracto():
    assert "predecir" in PredictorBase.__abstractmethods__


def test_formatter_enmascara_pii_y_excepciones():
    formatter = BankSecurityLogFormatter()
    record = logging.LogRecord(
        name="app.api",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="token Bearer eyJhbGciOiJIUzI1NiJ9.secret password=abc123",
        args=(),
        exc_info=None,
    )
    obj = json.loads(formatter.format(record))
    assert obj["nivel"] == "ERROR"
    assert obj["logger"] == "app.api"
    assert "MASKED_JWT_TOKEN" in obj["mensaje"]
    assert "MASKED_SECRET" in obj["mensaje"]
    assert "eyJhbGciOiJIUzI1NiJ9" not in obj["mensaje"]
    assert "abc123" not in obj["mensaje"]

    try:
        raise ValueError("boom de prueba")
    except ValueError:
        record2 = logging.LogRecord("app.api", logging.ERROR, __file__, 20, "fallo", (), None)
        record2.exc_info = sys.exc_info()
    obj2 = json.loads(formatter.format(record2))
    assert "excepcion" in obj2
    assert "ValueError" in obj2["excepcion"]


def test_mongo_estados_y_conexion(monkeypatch):
    class FakeDb:
        def __init__(self, nombre):
            self.nombre = nombre

        def __getitem__(self, key):
            return SimpleNamespace(nombre=key)

    class FakeMotorClient:
        def __init__(self, uri, **kwargs):
            self.uri = uri
            self.cerrado = False

        def __getitem__(self, nombre):
            return FakeDb(nombre)

        def close(self):
            self.cerrado = True

    monkeypatch.setattr("app.db.mongo.AsyncIOMotorClient", FakeMotorClient)
    s = Settings(mongo_uri="mongodb://test")
    m = Mongo(s)

    with pytest.raises(RuntimeError):
        _ = m.client
    with pytest.raises(RuntimeError):
        _ = m.source
    with pytest.raises(RuntimeError):
        _ = m.ml

    asyncio.run(m.connect())
    assert m.client.uri == "mongodb://test"
    assert m.source.nombre == s.source_db
    assert m.ml.nombre == s.ml_db
    assert m.lecturas.nombre == "lecturas_sensores"
    assert m.eventos.nombre == "eventos_metabolicos"
    assert m.pacientes.nombre == "pacientes"
    assert m.medicamentos.nombre == "medicamentos"
    assert m.features.nombre == "features_pacientes"
    assert m.modelos.nombre == "modelos"
    assert m.predicciones.nombre == "predicciones"
    assert m.eventos_confirmados.nombre == "eventos_confirmados"

    # connect() idempotente
    asyncio.run(m.connect())
    cliente = m.client
    asyncio.run(m.close())
    assert cliente.cerrado is True
    assert m._client is None


def test_crear_indices(fake_mongo):
    asyncio.run(_crear_indices(fake_mongo))


def test_lifespan_sin_mongo():
    app = SimpleNamespace()
    app.state = SimpleNamespace()

    async def _correr():
        async with lifespan(app):
            assert app.state.settings is not None

    asyncio.run(_correr())


def test_procesar_paciente_actualiza_features(fake_mongo):
    sembrar_paciente(fake_mongo, "P-WORKER", n_lecturas=60)
    predictor = PredictorService(fake_mongo, Settings(worker_sync_enabled=False))
    asyncio.run(_procesar_paciente(fake_mongo, predictor, "P-WORKER"))
    assert len(fake_mongo.features.docs) == 1
    assert fake_mongo.features.docs[0]["paciente_id"] == "P-WORKER"


def test_procesar_paciente_sin_datos_ignora(fake_mongo):
    predictor = PredictorService(fake_mongo, Settings(worker_sync_enabled=False))
    asyncio.run(_procesar_paciente(fake_mongo, predictor, "P-VACIO"))
    assert len(fake_mongo.features.docs) == 0


def test_cambios_procesa_change_stream(fake_mongo):
    sembrar_paciente(fake_mongo, "P-WS", n_lecturas=5)
    predictor = PredictorService(fake_mongo, Settings(worker_sync_enabled=False))

    class FakeStream:
        def __init__(self):
            self._emitido = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._emitido:
                self._emitido = True
                return {
                    "fullDocument": {
                        "meta": {"paciente_id": "P-WS"},
                        "timestamp": datetime.now(timezone.utc),
                    }
                }
            raise StopAsyncIteration

    fake_mongo.lecturas.watch = lambda **kwargs: FakeStream()
    asyncio.run(_cambios(fake_mongo, predictor))
    assert len(fake_mongo.features.docs) == 1


def test_run_retrain_con_resultado(monkeypatch):
    class FakeMongoStub:
        async def connect(self):
            pass

        async def close(self):
            pass

    class FakeRetrain:
        def __init__(self, *a, **k):
            pass

        async def entrenar(self, descripcion=None, retener_activo=True):
            return {"version": "v9", "total_muestras": 100, "metricas": {"f1": 0.9}}

    monkeypatch.setattr("app.worker.retrain.Mongo", lambda s: FakeMongoStub())
    monkeypatch.setattr("app.worker.retrain.RetrainService", FakeRetrain)
    asyncio.run(run_retrain("desc", retener_activo=False))


def test_run_retrain_sin_resultado(monkeypatch):
    class FakeMongoStub:
        async def connect(self):
            pass

        async def close(self):
            pass

    class FakeRetrain:
        def __init__(self, *a, **k):
            pass

        async def entrenar(self, descripcion=None, retener_activo=True):
            return None

    monkeypatch.setattr("app.worker.retrain.Mongo", lambda s: FakeMongoStub())
    monkeypatch.setattr("app.worker.retrain.RetrainService", FakeRetrain)
    asyncio.run(run_retrain(None, retener_activo=True))


def test_health_modelo_activo_con_mongo(client, monkeypatch):
    import app.api.routes.health as health_mod

    monkeypatch.setattr(health_mod, "settings", Settings(mongo_uri="mongodb://x"))

    async def _modelo():
        return SimpleNamespace(version="v-test")

    monkeypatch.setattr(client.app.state.predictor, "modelo_activo", _modelo)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["modeloActivo"] == "v-test"


def test_health_modelo_no_disponible_si_mongo_falla(client, monkeypatch):
    import app.api.routes.health as health_mod

    monkeypatch.setattr(health_mod, "settings", Settings(mongo_uri="mongodb://x"))

    async def _boom():
        raise RuntimeError("mongo caído")

    monkeypatch.setattr(client.app.state.predictor, "modelo_activo", _boom)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["modeloActivo"] == "no_disponible"


def test_ready_mongo_ok(client, fake_mongo, monkeypatch):
    import app.api.routes.health as health_mod

    monkeypatch.setattr(health_mod, "settings", Settings(mongo_uri="mongodb://x"))

    class AdminOk:
        async def command(self, cmd):
            return {"ok": 1.0}

    monkeypatch.setattr(type(fake_mongo), "client", property(lambda self: SimpleNamespace(admin=AdminOk())))
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["mongo"] is True
    assert r.json()["estado"] == "listo"


def test_ready_mongo_no_listo(client, fake_mongo, monkeypatch):
    import app.api.routes.health as health_mod

    monkeypatch.setattr(health_mod, "settings", Settings(mongo_uri="mongodb://x"))
    monkeypatch.setattr(type(fake_mongo), "client", property(lambda self: SimpleNamespace()))
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["mongo"] is False
    assert r.json()["estado"] == "no_listo"
