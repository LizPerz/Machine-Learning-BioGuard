import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, predict
from app.core.config import settings

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Cerebro predictivo de BioGuard. Recibe telemetría de pacientes y devuelve la probabilidad "
        "de crisis metabólica (0 a 1). Regla de negocio: probabilidad >= umbral (0.85 por defecto) "
        "se considera estado crítico."
    ),
    openapi_tags=[
        {"name": "prediccion", "description": "Predicción de riesgo metabólico"},
        {"name": "salud", "description": "Health check y metadata del servicio"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(predict.router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "servicio": settings.app_name,
        "version": settings.app_version,
        "documentacion": "/docs",
        "salud": f"{settings.api_prefix}/salud",
        "prediccion": f"{settings.api_prefix}/predicciones",
    }
