"""Preprocesamiento de texto compartido por entrenamiento e inferencia.

Al vivir en un único módulo (importado por training/train.py y por el backend) se evita
la inconsistencia entre entrenamiento e inferencia (training/serving skew).
"""

from __future__ import annotations

import re
import unicodedata

# Patrones de datos sensibles (gobernanza Fase I: anonimización donde sea posible).
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[CORREO]"),
    (re.compile(r"\b\d{18}\b"), "[CLABE]"),
    (re.compile(r"\b(?:\d[ -]?){15}\d\b"), "[TARJETA]"),
    (re.compile(r"\b(?:\+?52[ -]?)?(?:\d[ -]?){9}\d\b"), "[TELEFONO]"),
    (re.compile(r"\b(?:nip|pin|contrase[nñ]a|clave)\s*(?:es|:)?\s*\d{4,8}\b", re.IGNORECASE), "[DATO_SEGURIDAD]"),
]

_AMOUNT = re.compile(r"\$?\s?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\$\s?\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?\s?(?:pesos|mxn)\b", re.IGNORECASE)
_DATE = re.compile(
    r"\b(?:\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
    r"|\d{1,2}/\d{1,2}(?:/\d{2,4})?|ayer|hoy|anteayer|(?:el\s+)?(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo))\b",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?¿¡])\s+|\n+")
_NON_ALNUM = re.compile(r"[^a-z0-9ñ\[\]_ ]+")
_SPACES = re.compile(r"\s+")


def strip_accents(text: str) -> str:
    """Elimina acentos conservando la ñ (relevante en español)."""
    text = text.replace("ñ", "\0").replace("Ñ", "\1")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return text.replace("\0", "ñ").replace("\1", "Ñ")


def mask_pii(text: str) -> str:
    """Reemplaza correos, CLABE, tarjetas, teléfonos y NIP por marcadores."""
    for pattern, token in _PII_PATTERNS:
        text = pattern.sub(token, text)
    return text


def normalize_text(text: str) -> str:
    """Normalización usada por los vectorizadores TF-IDF (entrenamiento e inferencia)."""
    text = mask_pii(text or "")
    text = strip_accents(text.lower())
    text = _NON_ALNUM.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extrae montos y referencias temporales para el resumen del CRM."""
    masked = mask_pii(text)
    return {
        "montos": sorted({m.group(0).strip() for m in _AMOUNT.finditer(masked)}),
        "fechas": sorted({m.group(0).strip().lower() for m in _DATE.finditer(masked)}),
    }


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if len(s.strip()) > 3]
