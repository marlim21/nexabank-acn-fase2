"""Pruebas funcionales de la API REST (solicitudes correctas y respuestas esperadas)."""

UUID_LEN = 36


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["modelo_cargado"] is True
    assert "X-Request-ID" in r.headers


def test_suggest_flujo_completo(client):
    r = client.post("/api/v1/suggest", json={"mensaje": "Perdí mi tarjeta de débito ayer, quiero bloquearla", "top_k": 3})
    assert r.status_code == 200
    d = r.json()
    assert d["motivo"]["intent"] == "bloqueo_tarjeta"
    assert 0 <= d["motivo"]["confianza"] <= 1
    assert 1 <= len(d["fuentes"]) <= 3 and d["fuentes"][0]["id"] == "KB-005"
    assert d["sugerencia"].startswith("Gracias por comunicarse con NexaBank")
    assert d["sugerencia"].count("Gracias") == 1
    assert d["requiere_aprobacion_humana"] is True
    assert d["escalamiento_requerido"] is False
    assert len(d["id_sugerencia"]) == UUID_LEN
    assert d["modo_generacion"] in {"extractivo", "llm", "extractivo_fallback"}


def test_suggest_caso_sensible_escala(client):
    d = client.post("/api/v1/suggest", json={"mensaje": "Me llamaron del banco y les di mi NIP, ahora tengo cargos que no hice"}).json()
    assert d["motivo"]["intent"] == "posible_fraude"
    assert d["escalamiento_requerido"] is True
    assert any("Fraudes" in a for a in d["acciones_sugeridas"])


def test_suggest_enmascara_pii(client):
    d = client.post("/api/v1/suggest", json={"mensaje": "Bloqueen mi tarjeta 4152 3134 5678 9012, me la robaron"}).json()
    assert "4152" not in d["mensaje_enmascarado"] and "[TARJETA]" in d["mensaje_enmascarado"]


def test_suggest_top_k_respeta_limite(client):
    d = client.post("/api/v1/suggest", json={"mensaje": "Quiero un préstamo personal", "top_k": 1}).json()
    assert len(d["fuentes"]) == 1


def test_classify(client):
    r = client.post("/api/v1/classify", json={"texto": "Olvidé mi contraseña de la app"})
    assert r.status_code == 200
    assert r.json()["intent"] == "banca_digital"
    assert len(r.json()["alternativas"]) == 2


def test_summarize(client):
    turnos = [
        {"rol": "cliente", "texto": "Hola, me cobraron dos veces 899 pesos en Netflix el 3 de octubre."},
        {"rol": "agente", "texto": "Registré la aclaración con folio 55821."},
    ]
    r = client.post("/api/v1/summarize", json={"turnos": turnos})
    assert r.status_code == 200
    d = r.json()
    assert d["motivo"]["intent"] == "aclaracion_cargo"
    assert "899 pesos" in d["entidades"]["montos"] and "3 de octubre" in d["entidades"]["fechas"]
    assert d["resumen"].startswith("Motivo de contacto:") and "folio 55821" in d["resumen"]
    assert d["turnos_procesados"] == 2 and d["requiere_aprobacion_humana"] is True


def test_feedback_y_kpi_adopcion(client):
    sid = client.post("/api/v1/suggest", json={"mensaje": "Cuánto saldo tengo"}).json()["id_sugerencia"]
    before = client.get("/api/v1/metrics/adoption").json()["total"]
    r = client.post("/api/v1/feedback", json={"id_sugerencia": sid, "decision": "aprobada"})
    assert r.status_code == 200 and r.json()["registrado"] is True
    after = client.get("/api/v1/metrics/adoption").json()
    assert after["total"] == before + 1 and 0 < after["tasa_aceptacion"] <= 1


def test_model_info(client):
    d = client.get("/api/v1/model/info").json()
    assert d["nombre_modelo"] == "acn-intent-classifier" and len(d["clases"]) == 10
    assert "accuracy" in d["metricas_test"]


def test_documentacion_openapi(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    for path in ("/health", "/api/v1/suggest", "/api/v1/classify", "/api/v1/summarize", "/api/v1/feedback"):
        assert path in spec["paths"]


def test_frontend_servido(client):
    r = client.get("/")
    assert r.status_code == 200 and "Asistente Cognitivo NexaBank" in r.text
    assert client.get("/app.js").status_code == 200


def test_cors_origen_permitido(client):
    r = client.options("/api/v1/suggest", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8080"


def test_cors_origen_no_permitido(client):
    r = client.options("/api/v1/suggest", headers={"Origin": "http://sitio-malicioso.com", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
