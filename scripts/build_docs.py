"""Genera los PDF formales (portada + índice + contenido) a partir de los Markdown de docs/.

Uso: python scripts/build_docs.py [directorio_salida]
Requiere: markdown, playwright (Chromium). Los diagramas Mermaid se renderizan con mermaid.js (CDN).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else DOCS / "pdf"

DOCUMENTS = [
    ("manual_despliegue.md", "Manual_Despliegue_Cloud.pdf", "Manual de despliegue en la nube",
     "Procedimiento para trasladar la solución contenerizada a Azure Container Apps"),
    ("validacion_pruebas.md", "Documento_Validacion_Pruebas.pdf", "Documento de validación y pruebas",
     "Pruebas unitarias, de integración, funcionales, de casos extremos y validación del modelo"),
]

CSS = """
@page { size: A4; margin: 22mm 18mm 20mm 18mm; }
body { font-family: "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #17212f; }
h1 { font-size: 20pt; color: #1f4e79; }
h2 { font-size: 15pt; color: #ffffff; background: #1f4e79; padding: 6px 10px; margin-top: 22px; break-after: avoid; }
h3 { font-size: 12pt; color: #1f4e79; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 14px; font-size: 8.6pt; break-inside: auto; }
th { background: #1f4e79; color: #fff; text-align: left; padding: 5px 6px; }
td { border: 1px solid #dbe1ea; padding: 4px 6px; vertical-align: top; }
tr:nth-child(even) td { background: #f4f6f9; }
tr { break-inside: avoid; }
td:first-child { white-space: nowrap; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.6pt; background: #f1f3f6; padding: 0 3px; border-radius: 3px; }
pre { background: #0f1621; color: #e6ebf2; padding: 10px 12px; border-radius: 6px; font-size: 8.2pt; white-space: pre-wrap; word-break: break-word; break-inside: avoid; }
pre code { background: none; color: inherit; padding: 0; }
blockquote { border-left: 4px solid #b3261e; background: #fdecea; margin: 10px 0; padding: 8px 12px; }
img { max-width: 100%; display: block; margin: 8px auto; border: 1px solid #dbe1ea; break-inside: avoid; }
.mermaid { text-align: center; break-inside: avoid; margin: 10px 0; }
a { color: #1f4e79; word-break: break-all; }
.cover { height: 250mm; display: flex; flex-direction: column; justify-content: space-between; break-after: page; }
.cover .brand { font-size: 11pt; color: #5d6b7e; letter-spacing: .08em; text-transform: uppercase; }
.cover h1 { font-size: 28pt; margin: 0 0 8px; }
.cover .subtitle { font-size: 14pt; color: #5d6b7e; }
.cover .project { font-size: 16pt; margin-top: 28px; color: #17212f; font-weight: 600; }
.cover table td { border: none; background: none !important; font-size: 11pt; padding: 3px 0; }
.cover .note { font-size: 9pt; color: #5d6b7e; }
.toc { break-after: page; }
.toc ul { list-style: none; padding-left: 0; }
.toc li { margin: 3px 0; }
.toc ul ul { padding-left: 18px; }
"""


def strip_header(md_text: str) -> str:
    """Quita el bloque de título del Markdown (la portada lo sustituye) y conserva el resto."""
    lines = md_text.split("\n")
    i = 1
    while i < len(lines) and (not lines[i].strip() or lines[i].startswith("**") or "Elaborado por" in lines[i] or "Maestría" in lines[i]):
        i += 1
    return "\n".join(lines[i:])


def mermaid_blocks(md_text: str) -> str:
    return re.sub(r"```mermaid\n(.*?)```", lambda m: f'<div class="mermaid">\n{m.group(1)}</div>', md_text, flags=re.S)


def build_html(md_file: str, title: str, subtitle: str) -> str:
    body_md = mermaid_blocks(strip_header((DOCS / md_file).read_text(encoding="utf-8")))
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"], extension_configs={"toc": {"toc_depth": "2-2"}})
    body = md.convert(body_md)
    cover = f"""
<section class="cover">
  <div class="brand">Universidad Tecmilenio · Maestría en Inteligencia Artificial</div>
  <div>
    <h1>{title}</h1>
    <div class="subtitle">{subtitle}</div>
    <div class="project">Asistente Cognitivo NexaBank (ACN) — Proyecto de IA, Fase II</div>
  </div>
  <table>
    <tr><td><b>Materia:</b> Gestión de proyectos de inteligencia artificial</td></tr>
    <tr><td><b>Elaborado por:</b> Martin Limon</td></tr>
    <tr><td><b>Fecha:</b> Noviembre 2026 · Versión 1.0</td></tr>
    <tr><td><b>Repositorio:</b> https://github.com/marlim21/nexabank-acn-fase2</td></tr>
  </table>
  <div class="note">NexaBank es una empresa ficticia creada con fines académicos. Los datos utilizados son sintéticos.</div>
</section>
<section class="toc"><h1>Contenido</h1>{md.toc}</section>"""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<base href="{DOCS.as_uri()}/"><style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.0/dist/mermaid.min.js"></script></head>
<body>{cover}{body}
<script>mermaid.initialize({{startOnLoad: false, theme: "neutral", flowchart: {{htmlLabels: true}}}});
mermaid.run().then(() => document.body.setAttribute("data-ready", "1"));</script></body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for md_file, pdf_name, title, subtitle in DOCUMENTS:
            html_path = DOCS / f".{pdf_name}.html"
            html_path.write_text(build_html(md_file, title, subtitle), encoding="utf-8")
            page = browser.new_page()
            page.goto(html_path.as_uri())
            page.wait_for_selector("body[data-ready='1']", timeout=30_000)
            page.pdf(
                path=str(OUT / pdf_name), format="A4", print_background=True,
                display_header_footer=True,
                header_template='<div style="font-size:7pt;color:#5d6b7e;width:100%;padding:0 18mm;">Asistente Cognitivo NexaBank — Fase II</div>',
                footer_template='<div style="font-size:7pt;color:#5d6b7e;width:100%;text-align:right;padding:0 18mm;">Página <span class="pageNumber"></span> de <span class="totalPages"></span></div>',
                margin={"top": "22mm", "bottom": "20mm", "left": "18mm", "right": "18mm"},
            )
            page.close()
            html_path.unlink()
            print("PDF generado:", OUT / pdf_name)
        browser.close()


if __name__ == "__main__":
    main()
