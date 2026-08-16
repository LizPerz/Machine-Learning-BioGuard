"""Dependencias de la aplicación: singletons en app.state."""

from __future__ import annotations

from fastapi import Header, Request

from app.core.config import Settings
from app.core.security import verificar_token_servicio
from app.db.mongo import Mongo
from app.services.dashboard import DashboardService
from app.services.predictor import PredictorService
from app.services.retrain import RetrainService


def get_mongo(request: Request) -> Mongo:
    return request.app.state.mongo


def get_predictor(request: Request) -> PredictorService:
    return request.app.state.predictor


def get_dashboard(request: Request) -> DashboardService:
    return request.app.state.dashboard


def get_retrain(request: Request) -> RetrainService:
    return request.app.state.retrain


def auth_servicio(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Autenticación servicio-a-servicio (JWT firmado por el backend .NET).

    Segura por defecto: se exige el JWT salvo que se desactive de forma
    EXPLÍCITA con BIOGUARD_AUTH_DESHABILITADO=true (solo entornos de prueba).
    En producción, si no se configura BIOGUARD_SERVICE_TOKEN_SECRET, toda
    petición es rechazada (falla cerrando, nunca abierto).
    """
    s: Settings = request.app.state.settings
    if s.auth_deshabilitado:
        return
    verificar_token_servicio(authorization, s)
