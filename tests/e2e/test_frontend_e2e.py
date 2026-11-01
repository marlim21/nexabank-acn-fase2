"""Prueba extremo a extremo en navegador real (Chromium headless con Playwright):
usuario -> frontend -> API -> modelo -> resultado mostrado en pantalla.

Requiere: pip install playwright && python -m playwright install chromium
Ejecución: ACN_FRONTEND_URL=http://localhost:8080 pytest tests/e2e -v
Guarda capturas en evidencias/frontend_backend/.
"""

import os
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
URL = os.getenv("ACN_FRONTEND_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Define ACN_FRONTEND_URL para la prueba E2E")
SHOTS = Path(__file__).resolve().parents[2] / "evidencias" / "frontend_backend"


@pytest.fixture(scope="module")
def page():
    SHOTS.mkdir(parents=True, exist_ok=True)
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900}, color_scheme="light")
        yield pg
        browser.close()


def test_carga_y_estado_del_servicio(page):
    page.goto(URL)
    page.wait_for_selector("#status.status--ok", timeout=10_000)
    assert "Servicio activo" in page.inner_text("#status")
    page.wait_for_function("document.querySelector('#model-info').textContent.includes('accuracy')")
    page.screenshot(path=SHOTS / "01_consola_inicial.png", full_page=True)


def test_sugerencia_caso_normal(page):
    page.fill("#mensaje", "Perdí mi tarjeta de débito ayer en el metro, quiero bloquearla")
    page.click("#suggest-btn")
    page.wait_for_selector("#suggest-result:not([hidden])")
    assert "tarjeta" in page.inner_text("#r-motivo").lower()
    assert "KB-005" in page.inner_text("#r-fuentes")
    assert page.is_hidden("#escalation")
    page.screenshot(path=SHOTS / "02_sugerencia_bloqueo_tarjeta.png", full_page=True)


def test_aprobacion_humana_registra_kpi(page):
    page.click("[data-decision='aprobada']")
    page.wait_for_function("document.querySelector('#feedback-msg').textContent.includes('registrada')")
    assert page.is_disabled("[data-decision='rechazada']")
    page.screenshot(path=SHOTS / "03_decision_agente_registrada.png", full_page=True)


def test_caso_sensible_muestra_escalamiento(page):
    page.fill("#mensaje", "Me llamaron diciendo que eran del banco y les di el código que me llegó por SMS. Mi tarjeta es 4152 3134 5678 9012")
    page.click("#suggest-btn")
    page.wait_for_selector("#escalation:not([hidden])")
    assert "fraude" in page.inner_text("#r-motivo").lower()
    page.click("details summary")
    assert "[TARJETA]" in page.inner_text("#r-masked")
    page.screenshot(path=SHOTS / "04_caso_sensible_fraude_enmascarado.png", full_page=True)


def test_validacion_en_frontend(page):
    page.fill("#mensaje", "  ")
    page.click("#suggest-btn")
    assert "mínimo 3 caracteres" in page.inner_text("#suggest-error")
    page.screenshot(path=SHOTS / "05_validacion_campo_vacio.png")


def test_resumen_crm(page):
    page.click("#tab-summary")
    page.click("#summary-example")
    page.click("#summary-btn")
    page.wait_for_selector("#summary-result:not([hidden])")
    assert "Aclaración" in page.inner_text("#s-motivo")
    assert "899" in page.inner_text("#s-entidades")
    page.screenshot(path=SHOTS / "06_resumen_crm.png", full_page=True)


def test_error_de_formato_en_resumen(page):
    page.fill("#conversacion", "esto no tiene formato")
    page.click("#summary-btn")
    assert "formato válido" in page.inner_text("#summary-error")
