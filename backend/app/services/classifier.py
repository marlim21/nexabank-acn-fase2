"""Clasificador del motivo de contacto (TF-IDF palabras + caracteres -> Regresión Logística)."""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.preprocessing import normalize_text

INTENT_LABELS_ES: dict[str, str] = {
    "consulta_saldo": "Consulta de saldo y movimientos",
    "aclaracion_cargo": "Aclaración de cargo",
    "bloqueo_tarjeta": "Bloqueo / robo / extravío de tarjeta",
    "posible_fraude": "Posible fraude o suplantación",
    "transferencias": "Transferencias SPEI",
    "credito_prestamo": "Crédito y préstamos",
    "tarjeta_credito": "Tarjeta de crédito",
    "actualizacion_datos": "Actualización de datos",
    "banca_digital": "Banca digital y acceso",
    "queja_servicio": "Queja de servicio",
}

# Fase I: la IA no resuelve fraude ni quejas graves por sí sola -> escalamiento humano obligatorio.
SENSITIVE_INTENTS: frozenset[str] = frozenset({"posible_fraude", "queja_servicio"})


def build_pipeline(seed: int = 42, C: float = 8.0) -> Pipeline:
    features = FeatureUnion([
        ("words", TfidfVectorizer(preprocessor=normalize_text, ngram_range=(1, 2), sublinear_tf=True, min_df=1)),
        ("chars", TfidfVectorizer(preprocessor=normalize_text, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)),
    ])
    clf = LogisticRegression(C=C, max_iter=3000, class_weight="balanced", random_state=seed)
    return Pipeline([("features", features), ("clf", clf)])


@dataclass(frozen=True)
class IntentPrediction:
    intent: str
    label: str
    confidence: float
    alternatives: list[tuple[str, float]]
    sensitive: bool


class IntentClassifier:
    """Envoltura de inferencia sobre el pipeline entrenado y serializado con joblib."""

    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.classes: list[str] = list(pipeline.classes_)

    def predict(self, text: str, top_n: int = 3) -> IntentPrediction:
        probs = self.pipeline.predict_proba([text])[0]
        ranked = sorted(zip(self.classes, probs), key=lambda kv: kv[1], reverse=True)
        intent, conf = ranked[0]
        return IntentPrediction(
            intent=intent,
            label=INTENT_LABELS_ES.get(intent, intent),
            confidence=round(float(conf), 4),
            alternatives=[(k, round(float(v), 4)) for k, v in ranked[1:top_n]],
            sensitive=intent in SENSITIVE_INTENTS,
        )
