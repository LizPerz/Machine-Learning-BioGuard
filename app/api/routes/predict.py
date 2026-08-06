from fastapi import APIRouter, Depends

from app.api.deps import get_predictor
from app.schemas.prediccion import PrediccionRespuesta
from app.schemas.telemetria import TelemetriaEntrada
from app.services.predictor import PredictorBase

router = APIRouter(prefix="/predicciones", tags=["prediccion"])


@router.post(
    "",
    response_model=PrediccionRespuesta,
    status_code=201,
    summary="Predecir riesgo de crisis metabólica",
    description=(
        "Recibe una lectura de telemetría del paciente y devuelve la probabilidad (0 a 1) de crisis "
        "metabólica. Actualmente usa una implementación mock; se sustituirá por el modelo ML real."
    ),
)
async def crear_prediccion(
    telemetria: TelemetriaEntrada,
    predictor: PredictorBase = Depends(get_predictor),
) -> PrediccionRespuesta:
    return await predictor.predecir(telemetria)
