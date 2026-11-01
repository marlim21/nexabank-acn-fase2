"""Endpoints REST v1 del Asistente Cognitivo NexaBank."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas import (
    ClassifyRequest, ErrorResponse, FeedbackRequest, FeedbackResponse, Motive, SuggestRequest,
    SuggestResponse, SummarizeRequest, SummarizeResponse,
)
from app.services.assistant import ACNAssistant

logger = logging.getLogger("acn.api")
router = APIRouter(prefix="/api/v1", tags=["Asistente ACN"])

_ERRORS = {
    422: {"model": ErrorResponse, "description": "Datos de entrada inválidos"},
    503: {"model": ErrorResponse, "description": "Modelo no disponible"},
}


def _assistant(request: Request) -> ACNAssistant:
    assistant = getattr(request.app.state, "assistant", None)
    if assistant is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El modelo no está disponible")
    return assistant


@router.post("/suggest", response_model=SuggestResponse, responses=_ERRORS,
             summary="Sugerencia de respuesta (RAG) para el agente")
def suggest(body: SuggestRequest, request: Request) -> dict:
    result = _assistant(request).suggest(body.mensaje, body.top_k)
    logger.info("suggest intent=%s conf=%.3f fuentes=%d modo=%s escalar=%s", result["motivo"]["intent"],
                result["motivo"]["confianza"], len(result["fuentes"]), result["modo_generacion"], result["escalamiento_requerido"])
    return result


@router.post("/classify", response_model=Motive, responses=_ERRORS, summary="Clasificación del motivo de contacto")
def classify(body: ClassifyRequest, request: Request) -> dict:
    return _assistant(request).classify(body.texto)


@router.post("/summarize", response_model=SummarizeResponse, responses=_ERRORS,
             summary="Resumen del caso para el CRM (requiere aprobación humana)")
def summarize(body: SummarizeRequest, request: Request) -> dict:
    return _assistant(request).summarize([t.model_dump() for t in body.turnos])


@router.post("/feedback", response_model=FeedbackResponse, responses={**_ERRORS, 404: {"model": ErrorResponse}},
             summary="Registra la decisión del agente sobre una sugerencia (human-in-the-loop)")
def feedback(body: FeedbackRequest, request: Request) -> dict:
    assistant = _assistant(request)
    if not assistant.register_feedback(body.id_sugerencia, body.decision):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "id_sugerencia no encontrado")
    return {"registrado": True, "estadisticas": assistant.feedback.snapshot()}


@router.get("/metrics/adoption", summary="KPI de adopción: tasa de aceptación de sugerencias")
def adoption(request: Request) -> dict:
    return _assistant(request).feedback.snapshot()


@router.get("/model/info", responses=_ERRORS, summary="Información y métricas del modelo cargado")
def model_info(request: Request) -> dict:
    return _assistant(request).info()
