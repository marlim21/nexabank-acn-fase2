"""Pruebas de integración contra el sistema EN EJECUCIÓN (contenedores Docker).

Se ejecutan solo si se define ACN_BASE_URL. Ejemplos:
    ACN_BASE_URL=http://localhost:8080 pytest tests/test_integration.py   # vía frontend nginx -> API
    ACN_BASE_URL=http://localhost:8000 pytest tests/test_integration.py   # imagen única
"""

import os

import httpx
import pytest

BASE_URL = os.getenv("ACN_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="Define ACN_BASE_URL para probar el sistema desplegado")


@pytest.fixture(scope="module")
def http():
    with httpx.Client(base_url=BASE_URL, timeout=10) as c:
        yield c


def test_servicio_saludable(http):
    r = http.get("/health")
    assert r.status_code == 200 and r.json()["modelo_cargado"] is True


def test_frontend_disponible(http):
    r = http.get("/")
    assert r.status_code == 200 and "Asistente Cognitivo NexaBank" in r.text
    assert http.get("/app.js").status_code == 200


def test_frontend_a_api_a_modelo(http):
    """Mismo origen que usa el navegador: frontend -> (proxy) API -> modelo -> respuesta."""
    r = http.post("/api/v1/suggest", json={"mensaje": "Me robaron la tarjeta de crédito ayer"})
    assert r.status_code == 200
    d = r.json()
    assert d["motivo"]["intent"] == "bloqueo_tarjeta" and d["fuentes"][0]["id"] == "KB-005"
    assert "X-Request-ID" in r.headers


def test_flujo_humano_en_el_ciclo(http):
    sid = http.post("/api/v1/suggest", json={"mensaje": "Olvidé mi contraseña"}).json()["id_sugerencia"]
    r = http.post("/api/v1/feedback", json={"id_sugerencia": sid, "decision": "editada"})
    assert r.status_code == 200
    assert http.get("/api/v1/metrics/adoption").json()["editada"] >= 1


def test_resumen_crm(http):
    r = http.post("/api/v1/summarize", json={"turnos": [{"rol": "cliente", "texto": "Mandé 5,000 pesos por SPEI y no llegan"}]})
    assert r.status_code == 200 and r.json()["motivo"]["intent"] == "transferencias"


def test_errores_se_propagan_correctamente(http):
    assert http.post("/api/v1/suggest", json={"mensaje": ""}).status_code == 422
    assert http.post("/api/v1/suggest", content=b'{"mensaje": "' + b"a" * 70_000 + b'"}',
                     headers={"Content-Type": "application/json"}).status_code == 413


def test_documentacion_api(http):
    assert http.get("/docs").status_code == 200
    assert "/api/v1/suggest" in http.get("/openapi.json").json()["paths"]
