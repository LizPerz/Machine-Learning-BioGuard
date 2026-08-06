from app.services.predictor import PredictorBase, crear_predictor

predictor: PredictorBase = crear_predictor()


def get_predictor() -> PredictorBase:
    return predictor
