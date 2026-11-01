"""Pruebas unitarias del modelo: carga de artefactos, inferencia, recuperador y generador."""

import hashlib
import json

import pytest

from app.services.classifier import INTENT_LABELS_ES, SENSITIVE_INTENTS
from app.services.generator import NO_CONTEXT_REPLY, ResponseGenerator, extractive_answer


def test_artefactos_existen_y_hash_valido(root):
    art = root / "model" / "artifacts"
    meta = json.loads((art / "model_metadata.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((art / "intent_classifier.joblib").read_bytes()).hexdigest()
    assert digest == meta["classifier_sha256"]
    assert set(meta["classes"]) == set(INTENT_LABELS_ES)


def test_modelo_carga_una_vez_con_10_clases(assistant):
    assert len(assistant.classifier.classes) == 10
    assert assistant.confidence_threshold == pytest.approx(0.30)


@pytest.mark.parametrize("texto, esperado", [
    ("Me robaron la tarjeta en el camión", "bloqueo_tarjeta"),
    ("No reconozco un cargo de 500 pesos en mi cuenta", "aclaracion_cargo"),
    ("Me llamaron del banco y me pidieron el código del SMS", "posible_fraude"),
    ("Mandé una transferencia SPEI y no ha llegado", "transferencias"),
    ("Olvidé la contraseña de la app", "banca_digital"),
    ("Quiero poner una queja, el ejecutivo fue muy grosero", "queja_servicio"),
    ("Cuál es mi fecha de corte de la tarjeta de crédito", "tarjeta_credito"),
    ("Quiero cambiar mi correo electrónico registrado", "actualizacion_datos"),
    ("Me interesa un préstamo personal", "credito_prestamo"),
    ("Cuánto saldo tengo en mi cuenta", "consulta_saldo"),
])
def test_prediccion_casos_canonicos(assistant, texto, esperado):
    assert assistant.classifier.predict(texto).intent == esperado


def test_probabilidades_validas(assistant):
    probs = assistant.classifier.pipeline.predict_proba(["Perdí mi tarjeta"])[0]
    assert probs.sum() == pytest.approx(1.0)
    assert ((probs >= 0) & (probs <= 1)).all()


def test_bandera_sensible(assistant):
    pred = assistant.classifier.predict("Creo que me clonaron la tarjeta y hay compras que no hice")
    assert pred.intent in SENSITIVE_INTENTS and pred.sensitive


def test_recuperador_devuelve_articulo_esperado(assistant):
    res = assistant.retriever.search("Me robaron la tarjeta", top_k=3)
    assert res[0].article.id == "KB-005"
    assert res[0].score >= res[-1].score


def test_recuperador_con_pista_de_categoria(assistant):
    res = assistant.retriever.search("perdí mi tarjeta", top_k=1, category_hint="bloqueo_tarjeta")
    assert res[0].article.category == "bloqueo_tarjeta"


def test_recuperador_sin_coincidencias(assistant):
    assert assistant.retriever.search("xqzv wplk", top_k=3, min_score=0.08) == []


def test_generador_extractivo_usa_respuesta_aprobada(assistant):
    res = assistant.retriever.search("Me robaron la tarjeta", top_k=1)
    text = extractive_answer(res, escalate=False)
    assert res[0].article.customer_reply in text


def test_generador_sin_contexto():
    assert extractive_answer([], escalate=False) == NO_CONTEXT_REPLY


def test_generador_llm_falla_y_regresa_a_extractivo(assistant, monkeypatch):
    gen = ResponseGenerator(llm_enabled=False)
    gen.llm_enabled = True  # simula LLM habilitado con un proveedor que falla

    def boom(*_a, **_k):
        raise ConnectionError("sin red")

    monkeypatch.setattr(gen, "_generate_llm", boom)
    res = assistant.retriever.search("Perdí mi tarjeta", top_k=1)
    out = gen.generate("Perdí mi tarjeta", res, escalate=False)
    assert out.mode == "extractivo_fallback" and out.text


class _FakeBlock:
    def __init__(self, text):
        self.type, self.text = "text", text


class _FakeResponse:
    def __init__(self, stop_reason="end_turn", text="Borrador generado"):
        self.stop_reason, self.content = stop_reason, [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeClient:
    def __init__(self, response):
        self.beta = type("Beta", (), {})()
        self.beta.messages = _FakeMessages(response)


def test_generador_llm_usa_solo_fuentes_recuperadas(assistant):
    gen = ResponseGenerator(llm_enabled=False)
    gen.llm_enabled, gen._client = True, _FakeClient(_FakeResponse())
    res = assistant.retriever.search("Perdí mi tarjeta", top_k=2)
    out = gen.generate("Perdí mi tarjeta [TARJETA]", res, escalate=False)
    call = gen._client.beta.messages.calls[0]
    assert out.mode == "llm" and out.text == "Borrador generado"
    assert call["model"] == "claude-opus-5-5"
    assert res[0].article.title in call["messages"][0]["content"]
    assert "[TARJETA]" in call["messages"][0]["content"]  # al LLM solo llega el texto enmascarado


def test_generador_llm_rechazo_regresa_a_extractivo(assistant):
    gen = ResponseGenerator(llm_enabled=False)
    gen.llm_enabled, gen._client = True, _FakeClient(_FakeResponse(stop_reason="refusal", text=""))
    res = assistant.retriever.search("Perdí mi tarjeta", top_k=1)
    assert gen.generate("Perdí mi tarjeta", res, escalate=False).mode == "extractivo_fallback"
