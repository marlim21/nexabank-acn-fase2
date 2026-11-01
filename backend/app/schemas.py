"""Contrato de datos de la API (validación con Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from app.config import get_settings

_S = get_settings()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # variables desconocidas -> 422


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("el texto no puede estar vacío o contener solo espacios")
    return value.strip()


class SuggestRequest(_Strict):
    mensaje: StrictStr = Field(..., min_length=3, max_length=_S.max_text_chars, description="Mensaje del cliente (texto libre)",
                               examples=["Me aparece un cargo de 1,200 pesos en Amazon que yo no hice"])
    top_k: StrictInt = Field(_S.top_k_default, ge=1, le=5, description="Número de artículos a recuperar")

    _v = field_validator("mensaje")(_not_blank)


class ClassifyRequest(_Strict):
    texto: StrictStr = Field(..., min_length=3, max_length=_S.max_text_chars, examples=["Olvidé mi contraseña de la app"])

    _v = field_validator("texto")(_not_blank)


class Turn(_Strict):
    rol: Literal["cliente", "agente"]
    texto: StrictStr = Field(..., min_length=1, max_length=_S.max_text_chars)

    _v = field_validator("texto")(_not_blank)


class SummarizeRequest(_Strict):
    turnos: list[Turn] = Field(..., min_length=1, max_length=_S.max_turns)

    @field_validator("turnos")
    @classmethod
    def _needs_customer(cls, turns: list[Turn]) -> list[Turn]:
        if not any(t.rol == "cliente" for t in turns):
            raise ValueError("la conversación debe incluir al menos un turno del cliente")
        return turns


class FeedbackRequest(_Strict):
    id_sugerencia: StrictStr = Field(..., min_length=36, max_length=36)
    decision: Literal["aprobada", "editada", "rechazada"]


class Alternative(BaseModel):
    intent: str
    confianza: float


class Motive(BaseModel):
    intent: str
    etiqueta: str
    confianza: float
    alternativas: list[Alternative]
    sensible: bool
    confianza_baja: bool


class Source(BaseModel):
    id: str
    titulo: str
    categoria: str
    score: float


class SuggestResponse(BaseModel):
    id_sugerencia: str
    motivo: Motive
    sugerencia: str
    modo_generacion: str
    fuentes: list[Source]
    acciones_sugeridas: list[str]
    escalamiento_requerido: bool
    requiere_aprobacion_humana: bool
    mensaje_enmascarado: str
    latencia_ms: float


class Entities(BaseModel):
    montos: list[str]
    fechas: list[str]


class SummarizeResponse(BaseModel):
    motivo: Motive
    resumen: str
    entidades: Entities
    acciones_sugeridas: list[str]
    fuente: str | None
    escalamiento_requerido: bool
    requiere_aprobacion_humana: bool
    turnos_procesados: int


class FeedbackResponse(BaseModel):
    registrado: bool
    estadisticas: dict


class HealthResponse(BaseModel):
    status: Literal["ok", "degradado"]
    modelo_cargado: bool
    version: str
    entorno: str
    modo_generacion: str | None = None
    detalle: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detalle: str | list | None = None
