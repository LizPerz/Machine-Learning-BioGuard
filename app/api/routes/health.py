from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.schemas.common import SALIDA_CFG

router = APIRouter(tags=["salud"])


class SaludRespuesta(BaseModel):
    model_config = SALIDA_CFG

    estado: str
    servicio: str
    version: str
    modelo_activo: str
    umbral_critico: float


@router.get(
    "/salud",
    response_model=SaludRespuesta,
    summary="Health check del servicio",
    description="Útil para verificar disponibilidad y la versión del modelo activo desde el backend .NET.",
)
async def salud() -> SaludRespuesta:
    return SaludRespuesta(
        estado="ok",
        servicio=settings.app_name,
        version=settings.app_version,
        modelo_activo=settings.modelo_activo,
        umbral_critico=settings.umbral_critico,
    )
