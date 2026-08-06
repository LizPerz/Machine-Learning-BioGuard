from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import SALIDA_CFG


class NivelRiesgo(str, Enum):
    BAJO = "BAJO"
    MODERADO = "MODERADO"
    ALTO = "ALTO"
    CRITICO = "CRITICO"


class Contribucion(BaseModel):
    model_config = SALIDA_CFG

    senal: str = Field(..., description="Nombre legible de la señal vital")
    valor: float = Field(..., description="Valor recibido de la señal")
    severidad: float = Field(..., ge=0.0, le=1.0, description="0 = saludable, 1 = peligro extremo")


class PrediccionRespuesta(BaseModel):
    model_config = SALIDA_CFG

    paciente_id: str = Field(..., description="Identificador único del paciente")
    probabilidad: float = Field(..., ge=0.0, le=1.0, description="Probabilidad de crisis metabólica (0 a 1)")
    es_critico: bool = Field(..., description="True si probabilidad >= umbral crítico")
    nivel_riesgo: NivelRiesgo = Field(..., description="Nivel de riesgo derivado de la probabilidad")
    umbral_critico: float = Field(..., ge=0.0, le=1.0, description="Umbral configurado por regla de negocio")
    timestamp: datetime = Field(..., description="Momento en que se generó la predicción")
    modelo_id: str = Field(..., description="Identificador del modelo/variante usado")
    version: str = Field(..., description="Versión del servicio")
    mensaje: Optional[str] = Field(default=None, description="Mensaje legible para integraciones clínicas")
    contribuciones: Optional[list[Contribucion]] = Field(
        default=None, description="Desglose de severidad por señal vital (explicabilidad)"
    )
    explicacion: Optional[str] = Field(default=None, description="Metodología usada para el cálculo")
