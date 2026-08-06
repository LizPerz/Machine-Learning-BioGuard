import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.prediccion import PrediccionRespuesta
from app.schemas.telemetria import TelemetriaEntrada
from app.services.base import PredictorBase, _nivel_riesgo

logger = logging.getLogger(__name__)


class PredictorMock(PredictorBase):
    def __init__(self, probabilidad: float, umbral: float, modelo_id: str, version: str):
        self.probabilidad = probabilidad
        self.umbral = umbral
        self.modelo_id = modelo_id
        self.version = version

    async def predecir(self, telemetria: TelemetriaEntrada) -> PrediccionRespuesta:
        logger.info(
            "PredictorMock recibiendo telemetría | paciente=%s | fc=%s | temp=%s | spo2=%s",
            telemetria.paciente_id,
            telemetria.frecuencia_cardiaca,
            telemetria.temperatura,
            telemetria.saturacion_oxigeno,
        )
        es_critico = self.probabilidad >= self.umbral
        return PrediccionRespuesta(
            paciente_id=telemetria.paciente_id,
            probabilidad=self.probabilidad,
            es_critico=es_critico,
            nivel_riesgo=_nivel_riesgo(self.probabilidad, self.umbral),
            umbral_critico=self.umbral,
            timestamp=datetime.now(timezone.utc),
            modelo_id=self.modelo_id,
            version=self.version,
            mensaje=(
                "ALERTA: probabilidad de crisis metabólica por encima del umbral crítico"
                if es_critico
                else "Estado estable: probabilidad por debajo del umbral crítico"
            ),
        )


def crear_predictor() -> PredictorBase:
    if settings.predictor_activo == "baseline":
        from app.services.baseline import PredictorBaseline

        return PredictorBaseline(
            umbral=settings.umbral_critico,
            modelo_id=settings.modelo_activo,
            version=settings.app_version,
        )
    return PredictorMock(
        probabilidad=settings.probabilidad_mock,
        umbral=settings.umbral_critico,
        modelo_id=settings.modelo_activo,
        version=settings.app_version,
    )
