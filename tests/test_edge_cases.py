"""Pruebas de casos extremos: entradas inválidas, límites y fallas de componentes."""

import dataclasses
import shutil
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import get_settings

SUGGEST = "/api/v1/suggest"


@pytest.mark.parametrize("payload, campo", [
    ({}, "mensaje"),                                   # campo faltante
    ({"mensaje": ""}, "mensaje"),                      # vacío
    ({"mensaje": "     "}, "mensaje"),                 # solo espacios
    ({"mensaje": None}, "mensaje"),                    # nulo
    ({"mensaje": 12345}, "mensaje"),                   # tipo incorrecto
    ({"mensaje": ["hola"]}, "mensaje"),                # lista en lugar de texto
    ({"mensaje": "ok"}, "mensaje"),                    # demasiado corto
    ({"mensaje": "a" * 2001}, "mensaje"),              # excede longitud máxima
    ({"mensaje": "Perdí mi tarjeta", "top_k": 0}, "top_k"),      # fuera de rango
    ({"mensaje": "Perdí mi tarjeta", "top_k": 99}, "top_k"),     # fuera de rango
    ({"mensaje": "Perdí mi tarjeta", "top_k": "3"}, "top_k"),    # tipo incorrecto
    ({"mensaje": "Perdí mi tarjeta", "edad": 30}, "edad"),       # variable desconocida
])
def test_validacion_entradas_422(client, payload, campo):
    r = client.post(SUGGEST, json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "datos_invalidos"
    assert any(d["campo"] == campo for d in body["detalle"])


def test_error_no_refleja_datos_enviados(client):
    r = client.post(SUGGEST, json={"mensaje": 4152313456789012})
    assert "4152313456789012" not in r.text


def test_json_malformado(client):
    r = client.post(SUGGEST, content=b'{"mensaje": "hola', headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_cuerpo_no_json(client):
    r = client.post(SUGGEST, content=b"mensaje=hola", headers={"Content-Type": "text/plain"})
    assert r.status_code == 422


def test_solicitud_excesivamente_grande_413(client):
    r = client.post(SUGGEST, content=b'{"mensaje": "' + b"a" * 70_000 + b'"}', headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"] == "solicitud_demasiado_grande"


def test_metodo_no_permitido(client):
    assert client.get(SUGGEST).status_code == 405


def test_ruta_inexistente(client):
    assert client.get("/api/v1/no-existe").status_code == 404


@pytest.mark.parametrize("mensaje", [
    "asdkjh qwpoeiru zmxncb",                     # texto sin sentido
    "🙂🙂🙂 ???",                                  # emojis / símbolos
    "<script>alert('x')</script> DROP TABLE clientes;",  # intento de inyección
    "4152 3134 5678 9012",                        # solo datos sensibles
    "ok " * 600,                                  # texto largo dentro del límite
])
def test_entradas_atipicas_no_rompen_el_servicio(client, mensaje):
    r = client.post(SUGGEST, json={"mensaje": mensaje[:2000]})
    assert r.status_code == 200
    assert r.json()["requiere_aprobacion_humana"] is True


def test_texto_sin_sentido_marca_confianza_baja(client):
    d = client.post(SUGGEST, json={"mensaje": "asdkjh qwpoeiru zmxncb"}).json()
    assert d["motivo"]["confianza_baja"] is True


def test_summarize_sin_turno_de_cliente(client):
    r = client.post("/api/v1/summarize", json={"turnos": [{"rol": "agente", "texto": "Hola"}]})
    assert r.status_code == 422


def test_summarize_rol_invalido(client):
    r = client.post("/api/v1/summarize", json={"turnos": [{"rol": "supervisor", "texto": "Hola"}]})
    assert r.status_code == 422


def test_summarize_lista_vacia_y_demasiados_turnos(client):
    assert client.post("/api/v1/summarize", json={"turnos": []}).status_code == 422
    turnos = [{"rol": "cliente", "texto": "Perdí mi tarjeta"}] * 51
    assert client.post("/api/v1/summarize", json={"turnos": turnos}).status_code == 422


def test_feedback_id_desconocido_404(client):
    r = client.post("/api/v1/feedback", json={"id_sugerencia": "00000000-0000-0000-0000-000000000000", "decision": "aprobada"})
    assert r.status_code == 404


def test_feedback_decision_invalida(client):
    r = client.post("/api/v1/feedback", json={"id_sugerencia": "00000000-0000-0000-0000-000000000000", "decision": "tal vez"})
    assert r.status_code == 422


# ---------- Fallas de componentes: modelo o configuración no disponibles ----------

@contextmanager
def _client_with(monkeypatch, **overrides):
    """Levanta la app con una configuración alterada y restaura el estado compartido al salir."""
    state = main_module.app.state
    saved = (getattr(state, "assistant", None), getattr(state, "load_error", None))
    monkeypatch.setattr(main_module, "settings", dataclasses.replace(get_settings(), **overrides))
    try:
        with TestClient(main_module.app) as c:
            yield c
    finally:
        state.assistant, state.load_error = saved


def test_modelo_no_disponible_503(monkeypatch, tmp_path):
    with _client_with(monkeypatch, artifacts_dir=tmp_path) as c:
        h = c.get("/health")
        assert h.status_code == 503 and h.json()["status"] == "degradado"
        r = c.post(SUGGEST, json={"mensaje": "Perdí mi tarjeta"})
        assert r.status_code == 503 and r.json()["error"] == "modelo_no_disponible"


def test_artefacto_alterado_no_se_carga(monkeypatch, tmp_path, root):
    src = root / "model" / "artifacts"
    for f in src.iterdir():
        shutil.copy(f, tmp_path / f.name)
    with (tmp_path / "intent_classifier.joblib").open("ab") as fh:
        fh.write(b"manipulado")
    with _client_with(monkeypatch, artifacts_dir=tmp_path) as c:
        h = c.get("/health")
        assert h.status_code == 503 and "hash" in h.json()["detalle"]


def test_base_de_conocimiento_no_disponible(monkeypatch, tmp_path):
    with _client_with(monkeypatch, kb_path=tmp_path / "no_existe.json") as c:
        assert c.get("/health").status_code == 503


def test_metadatos_corruptos(monkeypatch, tmp_path, root):
    src = root / "model" / "artifacts"
    for f in src.iterdir():
        shutil.copy(f, tmp_path / f.name)
    (tmp_path / "model_metadata.json").write_text("{corrupto", encoding="utf-8")
    with _client_with(monkeypatch, artifacts_dir=tmp_path) as c:
        assert c.get("/health").status_code == 503
