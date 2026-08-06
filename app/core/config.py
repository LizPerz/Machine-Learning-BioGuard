from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BIOGUARD_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "BioGuard ML Service"
    app_version: str = "0.1.0"
    debug: bool = True
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    umbral_critico: float = 0.85
    probabilidad_mock: float = 0.90
    modelo_activo: str = "baseline-v0"
    predictor_activo: Literal["mock", "baseline"] = "baseline"
    baseline_peso_peor_senal: float = 0.6

    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
