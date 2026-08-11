from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BIOGUARD_", env_file=".env", extra="ignore")

    app_env: str = "development"
    app_version: str = "2.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    mongo_uri: str = ""
    source_db: str = "bioguard"
    ml_db: str = "bioguard_ml"

    service_audience: str = "ml-service"
    service_issuer: str = "BioGuardApi"
    service_token_secret: str = ""

    predictor_activo: str = "baseline"
    umbral_critico: float = 0.85
    baseline_peso_peor_senal: float = 0.6
    probabilidad_mock: float = 0.85
    window_size: int = 12
    window_horizon_min: int = 120
    min_lecturas_baseline: int = 50
    modelo_min_muestras: int = 30
    cors_origins: list[str] = ["*"]

    worker_sync_enabled: bool = False
    features_ttl_days: int = 90
    retrain_cron: str = "0 3 * * 0"

    rate_limit_ml: str = "100/minute"

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def is_production(self) -> bool:
        return not self.is_development


@lru_cache
def get_settings() -> Settings:
    return Settings()
