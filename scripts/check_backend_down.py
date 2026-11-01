"""Caso extremo X-19: el frontend debe informar con claridad cuando el backend no está disponible.
Precondición: frontend en ejecución y servicio api DETENIDO (lo hace scripts/validate_docker.sh)."""

import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 700}, color_scheme="light")
    page.goto(URL)
    page.wait_for_selector("#status.status--down", timeout=20_000)
    page.fill("#mensaje", "Perdí mi tarjeta")
    page.click("#suggest-btn")
    page.wait_for_selector("#suggest-error:not([hidden])")
    message = page.inner_text("#suggest-error")
    page.screenshot(path="evidencias/frontend_backend/07_backend_no_disponible.png")
    browser.close()

print(f"Estado mostrado: Servicio no disponible | Mensaje: {message}")
assert "No hay comunicación con el backend" in message, message
print("X-19 APROBADO")
