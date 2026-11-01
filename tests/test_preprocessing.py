"""Pruebas unitarias del preprocesamiento (compartido por entrenamiento e inferencia)."""

import pytest

from app.services.preprocessing import extract_entities, mask_pii, normalize_text, split_sentences, strip_accents


def test_strip_accents_preserva_enie():
    assert strip_accents("Contraseña olvidé ÁÉÍÓÚ") == "Contraseña olvide AEIOU"


def test_normalize_text_minusculas_sin_signos():
    assert normalize_text("¡Hola! ¿Cuánto TENGO en mi cuenta?") == "hola cuanto tengo en mi cuenta"


def test_normalize_text_vacio_o_none():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


@pytest.mark.parametrize("texto, token", [
    ("mi tarjeta es 4152 3134 5678 9012", "[TARJETA]"),
    ("mi tarjeta es 4152313456789012", "[TARJETA]"),
    ("la CLABE 012180001234567891 está mal", "[CLABE]"),
    ("escríbanme a juan.perez@correo.com", "[CORREO]"),
    ("mi cel es 55 1234 5678", "[TELEFONO]"),
    ("mi nip es 1234", "[DATO_SEGURIDAD]"),
])
def test_mask_pii(texto, token):
    masked = mask_pii(texto)
    assert token in masked
    assert sum(ch.isdigit() for ch in masked) == 0  # ningún dígito sensible sobrevive


def test_mask_pii_no_altera_montos():
    assert mask_pii("me cobraron 1,200 pesos") == "me cobraron 1,200 pesos"


def test_extract_entities_montos_y_fechas():
    ent = extract_entities("Me cobraron 1,200 pesos el 3 de octubre y $350 ayer")
    assert "1,200" in ent["montos"] and "$350" in ent["montos"]
    assert "3 de octubre" in ent["fechas"] and "ayer" in ent["fechas"]


def test_split_sentences():
    assert split_sentences("Hola. Me robaron la tarjeta. ¿Qué hago?") == ["Hola.", "Me robaron la tarjeta.", "¿Qué hago?"]
