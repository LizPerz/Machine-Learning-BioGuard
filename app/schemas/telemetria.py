from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ENTRADA_CFG


class TelemetriaEntrada(BaseModel):
    model_config = ENTRADA_CFG

    paciente_id: str = Field(..., min_length=1, max_length=64, description="Identificador único del paciente")
    frecuencia_cardiaca: int = Field(..., ge=20, le=250, description="Pulsaciones por minuto")
    temperatura: float = Field(..., ge=30.0, le=45.0, description="Temperatura corporal en °C")
    saturacion_oxigeno: float = Field(..., ge=50.0, le=100.0, description="Saturación de oxígeno en % (SpO2)")
    frecuencia_respiratoria: int = Field(..., ge=4, le=60, description="Respiraciones por minuto")
    presion_sistolica: Optional[int] = Field(default=None, ge=50, le=260, description="Presión arterial sistólica en mmHg")
    presion_diastolica: Optional[int] = Field(default=None, ge=30, le=160, description="Presión arterial diastólica en mmHg")
    glucosa: Optional[float] = Field(default=None, ge=20.0, le=600.0, description="Glucosa en mg/dL")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Momento de la medición (ISO 8601)")
    dispositivo: Optional[str] = Field(default=None, max_length=64, description="Identificador del dispositivo/smartwatch")

    @model_validator(mode="after")
    def _validar_presiones(self) -> "TelemetriaEntrada":
        if (
            self.presion_sistolica is not None
            and self.presion_diastolica is not None
            and self.presion_sistolica <= self.presion_diastolica
        ):
            raise ValueError("la presión sistólica debe ser mayor que la diastólica")
        return self
