import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.prediccion import Contribucion, PrediccionRespuesta
from app.schemas.telemetria import TelemetriaEntrada
from app.services.base import PredictorBase, _nivel_riesgo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RangoVital:
    etiqueta: str
    minimo_saludable: float
    maximo_saludable: float
    minimo_extremo: float
    maximo_extremo: float
    peso: float


RANGOS_VITALES: dict[str, RangoVital] = {
    "frecuencia_cardiaca": RangoVital("Frecuencia cardíaca", 60.0, 100.0, 35.0, 170.0, 0.25),
    "temperatura": RangoVital("Temperatura", 36.0, 37.5, 34.0, 42.0, 0.20),
    "saturacion_oxigeno": RangoVital("Saturación de oxígeno", 95.0, 100.0, 60.0, 100.0, 0.25),
    "frecuencia_respiratoria": RangoVital("Frecuencia respiratoria", 12.0, 20.0, 6.0, 40.0, 0.15),
    "presion_sistolica": RangoVital("Presión sistólica", 90.0, 140.0, 70.0, 200.0, 0.10),
    "presion_diastolica": RangoVital("Presión diastólica", 60.0, 90.0, 40.0, 120.0, 0.05),
    "glucosa": RangoVital("Glucosa", 70.0, 140.0, 40.0, 400.0, 0.20),
}


def _severidad(valor: float, rango: RangoVital) -> float:
    if valor < rango.minimo_saludable:
        denom = rango.minimo_saludable - rango.minimo_extremo
        if denom <= 0:
            return 1.0
        return max(0.0, min(1.0, (rango.minimo_saludable - valor) / denom))
    if valor > rango.maximo_saludable:
        denom = rango.maximo_extremo - rango.maximo_saludable
        if denom <= 0:
            return 1.0
        return max(0.0, min(1.0, (valor - rango.maximo_saludable) / denom))
    return 0.0


def _scoring(telemetria: TelemetriaEntrada) -> tuple[float, list[Contribucion]]:
    contribuciones: list[Contribucion] = []
    severidad_ponderada = 0.0
    peso_total = 0.0
    max_severidad = 0.0

    for clave, rango in RANGOS_VITALES.items():
        valor = getattr(telemetria, clave)
        if valor is None:
            continue
        severidad = _severidad(float(valor), rango)
        contribuciones.append(
            Contribucion(
                senal=rango.etiqueta,
                valor=round(float(valor), 4),
                severidad=round(severidad, 4),
            )
        )
        severidad_ponderada += rango.peso * severidad
        peso_total += rango.peso
        max_severidad = max(max_severidad, severidad)

    if peso_total <= 0:
        raise ValueError("no se recibieron señales vitales suficientes para calcular el riesgo")

    severidad_media = severidad_ponderada / peso_total
    efectiva = (
        settings.baseline_peso_peor_senal * max_severidad
        + (1.0 - settings.baseline_peso_peor_senal) * severidad_media
    )
    logit = 6.0 * efectiva - 3.0
    probabilidad = 1.0 / (1.0 + math.exp(-logit))
    return round(probabilidad, 4), contribuciones


class PredictorBaseline(PredictorBase):
    def __init__(self, umbral: float, modelo_id: str, version: str):
        self.umbral = umbral
        self.modelo_id = modelo_id
        self.version = version

    async def predecir(self, telemetria: TelemetriaEntrada) -> PrediccionRespuesta:
        probabilidad, contribuciones = _scoring(telemetria)
        es_critico = probabilidad >= self.umbral
        logger.info(
            "PredictorBaseline | paciente=%s | probabilidad=%s | es_critico=%s",
            telemetria.paciente_id,
            probabilidad,
            es_critico,
        )
        return PrediccionRespuesta(
            paciente_id=telemetria.paciente_id,
            probabilidad=probabilidad,
            es_critico=es_critico,
            nivel_riesgo=_nivel_riesgo(probabilidad, self.umbral),
            umbral_critico=self.umbral,
            timestamp=datetime.now(timezone.utc),
            modelo_id=self.modelo_id,
            version=self.version,
            mensaje=(
                "ALERTA: probabilidad de crisis metabólica por encima del umbral crítico"
                if es_critico
                else "Estado estable: probabilidad por debajo del umbral crítico"
            ),
            contribuciones=contribuciones,
            explicacion=(
                "Baseline v0: severidad por desviación de rangos vitales "
                "(peor señal + media ponderada) convertida a probabilidad logística."
            ),
        )
