"""Orquestador del Asistente Cognitivo NexaBank: clasificación + recuperación + generación.

El modelo se carga UNA sola vez al iniciar el servicio (ver main.py, lifespan) y se
reutiliza en todas las solicitudes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path

import joblib
import sklearn

from app.config import Settings
from app.services.classifier import IntentClassifier
from app.services.generator import ResponseGenerator
from app.services.preprocessing import extract_entities, mask_pii, split_sentences
from app.services.retriever import KnowledgeBaseRetriever, load_articles

logger = logging.getLogger("acn.assistant")

CLASSIFIER_FILE = "intent_classifier.joblib"
METADATA_FILE = "model_metadata.json"
METRICS_FILE = "metrics.json"
MAX_TRACKED_SUGGESTIONS = 10_000


class ModelLoadError(RuntimeError):
    """El modelo o sus archivos de configuración no están disponibles o no son válidos."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class FeedbackStats:
    """KPI de gobernanza (Fase I): tasa de aceptación/edición/rechazo de sugerencias."""

    counts: Counter
    lock: threading.Lock

    def add(self, decision: str) -> None:
        with self.lock:
            self.counts[decision] += 1

    def snapshot(self) -> dict:
        with self.lock:
            total = sum(self.counts.values())
            data = {k: self.counts.get(k, 0) for k in ("aprobada", "editada", "rechazada")}
        rate = lambda k: round(data[k] / total, 4) if total else 0.0  # noqa: E731
        return {"total": total, **data, "tasa_aceptacion": rate("aprobada"), "tasa_edicion": rate("editada"), "tasa_rechazo": rate("rechazada")}


class ACNAssistant:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.metadata, self.metrics = self._load_metadata(settings.artifacts_dir)
        self.classifier = IntentClassifier(self._load_classifier(settings.artifacts_dir))
        self.confidence_threshold = settings.confidence_threshold or float(self.metadata.get("confidence_threshold", 0.30))
        try:
            self.articles = load_articles(settings.kb_path)
        except (OSError, ValueError, KeyError) as exc:
            raise ModelLoadError(f"Base de conocimiento no disponible: {settings.kb_path.name}") from exc
        self.retriever = KnowledgeBaseRetriever(self.articles)
        self.generator = ResponseGenerator(settings.llm_enabled, settings.llm_model, settings.llm_timeout_s)
        self.feedback = FeedbackStats(Counter(), threading.Lock())
        self._issued: OrderedDict[str, str] = OrderedDict()
        logger.info("Modelo cargado: %s clases, %s artículos, generación=%s", len(self.classifier.classes), len(self.articles), self.generator.mode)

    # ---------- carga ----------
    def _load_metadata(self, artifacts_dir: Path) -> tuple[dict, dict]:
        try:
            metadata = json.loads((artifacts_dir / METADATA_FILE).read_text(encoding="utf-8"))
            metrics = json.loads((artifacts_dir / METRICS_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelLoadError("Metadatos del modelo no disponibles o corruptos") from exc
        return metadata, metrics

    def _load_classifier(self, artifacts_dir: Path):
        path = artifacts_dir / CLASSIFIER_FILE
        if not path.exists():
            raise ModelLoadError(f"No se encontró el artefacto del modelo: {CLASSIFIER_FILE}")
        # joblib usa pickle: se verifica la integridad antes de deserializar.
        if _sha256(path) != self.metadata.get("classifier_sha256"):
            raise ModelLoadError("El hash del artefacto no coincide con model_metadata.json")
        trained_with = self.metadata.get("sklearn_version")
        if trained_with != sklearn.__version__:
            logger.warning("Modelo entrenado con scikit-learn %s y servido con %s", trained_with, sklearn.__version__)
        return joblib.load(path)

    # ---------- casos de uso ----------
    def classify(self, text: str) -> dict:
        masked = mask_pii(text)
        pred = self.classifier.predict(masked)
        return {
            "intent": pred.intent,
            "etiqueta": pred.label,
            "confianza": pred.confidence,
            "alternativas": [{"intent": k, "confianza": v} for k, v in pred.alternatives],
            "sensible": pred.sensitive,
            "confianza_baja": pred.confidence < self.confidence_threshold,
        }

    def suggest(self, message: str, top_k: int) -> dict:
        start = time.perf_counter()
        masked = mask_pii(message)
        motive = self.classify(masked)
        retrieved = self.retriever.search(masked, top_k=top_k, category_hint=motive["intent"], min_score=self.settings.retrieval_min_score)
        generation = self.generator.generate(masked, retrieved, escalate=motive["sensible"])
        suggestion_id = str(uuid.uuid4())
        self._issued[suggestion_id] = motive["intent"]
        while len(self._issued) > MAX_TRACKED_SUGGESTIONS:  # memoria acotada
            self._issued.popitem(last=False)
        actions = list(retrieved[0].article.next_steps) if retrieved else ["Validar la consulta con un supervisor"]
        return {
            "id_sugerencia": suggestion_id,
            "motivo": motive,
            "sugerencia": generation.text,
            "modo_generacion": generation.mode,
            "fuentes": [
                {"id": r.article.id, "titulo": r.article.title, "categoria": r.article.category, "score": r.score} for r in retrieved
            ],
            "acciones_sugeridas": actions,
            "escalamiento_requerido": motive["sensible"],
            "requiere_aprobacion_humana": True,
            "mensaje_enmascarado": masked,
            "latencia_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    def summarize(self, turns: list[dict]) -> dict:
        customer = [mask_pii(t["texto"]) for t in turns if t["rol"] == "cliente"]
        agent = [mask_pii(t["texto"]) for t in turns if t["rol"] == "agente"]
        customer_text = " ".join(customer)
        motive = self.classify(customer_text)
        key = self._key_sentences(customer, k=2)
        retrieved = self.retriever.search(customer_text, top_k=1, category_hint=motive["intent"], min_score=self.settings.retrieval_min_score)
        agent_last = split_sentences(agent[-1])[-1] if agent and split_sentences(agent[-1]) else None
        summary = f"Motivo de contacto: {motive['etiqueta']}. El cliente indica: {' '.join(key)}"
        if agent_last:
            summary += f" Última acción del agente: {agent_last}"
        return {
            "motivo": motive,
            "resumen": summary,
            "entidades": extract_entities(" ".join(customer + agent)),
            "acciones_sugeridas": list(retrieved[0].article.next_steps) if retrieved else [],
            "fuente": retrieved[0].article.id if retrieved else None,
            "escalamiento_requerido": motive["sensible"],
            "requiere_aprobacion_humana": True,
            "turnos_procesados": len(turns),
        }

    def _key_sentences(self, messages: list[str], k: int) -> list[str]:
        sentences = [s for m in messages for s in (split_sentences(m) or [m])]
        if len(sentences) <= k:
            return sentences
        weights = self.retriever.vectorizer.transform(sentences).sum(axis=1).A1
        top = sorted(sorted(range(len(sentences)), key=lambda i: -weights[i])[:k])
        return [sentences[i] for i in top]

    def register_feedback(self, suggestion_id: str, decision: str) -> bool:
        if suggestion_id not in self._issued:
            return False
        self.feedback.add(decision)
        return True

    def info(self) -> dict:
        return {
            "nombre_modelo": self.metadata.get("model_name"),
            "version_modelo": self.metadata.get("model_version"),
            "entrenado_en": self.metadata.get("trained_at"),
            "algoritmo": self.metadata.get("algorithm"),
            "sklearn_version": self.metadata.get("sklearn_version"),
            "clases": self.classifier.classes,
            "articulos_base_conocimiento": len(self.articles),
            "modo_generacion": self.generator.mode,
            "umbral_confianza": self.confidence_threshold,
            "metricas_test": self.metrics.get("classifier", {}).get("test", {}),
            "metricas_recuperador": self.metrics.get("retriever", {}),
        }
