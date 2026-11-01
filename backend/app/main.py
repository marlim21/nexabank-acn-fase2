"""Punto de entrada FastAPI del Asistente Cognitivo NexaBank (ACN) — Fase II."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.config import get_settings
from app.schemas import HealthResponse
from app.services.assistant import ACNAssistant, ModelLoadError

settings = get_settings()
MAX_BODY_BYTES = 64 * 1024

logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("acn")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # El modelo se carga una sola vez al arrancar; si falla, el servicio queda "degradado" (503).
    try:
        app.state.assistant = ACNAssistant(settings)
        app.state.load_error = None
    except ModelLoadError as exc:
        logger.error("No se pudo cargar el modelo: %s", exc)
        app.state.assistant, app.state.load_error = None, str(exc)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "API del Asistente Cognitivo NexaBank (empresa ficticia, proyecto académico). "
        "Clasifica el motivo de contacto, recupera artículos de la base de conocimiento (RAG), "
        "sugiere una respuesta y resume el caso. Toda salida requiere aprobación de un agente humano."
    ),
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.middleware("http")
async def guard_and_log(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse({"error": "solicitud_demasiado_grande", "detalle": f"Máximo {MAX_BODY_BYTES} bytes"}, status_code=413)
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    # No se registra el contenido de los mensajes (privacidad): solo metadatos.
    logger.info("req=%s %s %s -> %s %.1fms", request_id, request.method, request.url.path, response.status_code, (time.perf_counter() - start) * 1000)
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    # No se devuelve el valor recibido ("input") para no reflejar datos sensibles.
    details = [{"campo": ".".join(str(p) for p in e["loc"][1:]) or "body", "error": e["msg"]} for e in exc.errors()]
    return JSONResponse({"error": "datos_invalidos", "detalle": details}, status_code=422)


@app.exception_handler(StarletteHTTPException)
async def http_handler(_: Request, exc: StarletteHTTPException):
    codes = {404: "no_encontrado", 405: "metodo_no_permitido", 503: "modelo_no_disponible"}
    return JSONResponse({"error": codes.get(exc.status_code, "error_http"), "detalle": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception):
    logger.exception("Error no controlado: %s", type(exc).__name__)
    return JSONResponse({"error": "error_interno", "detalle": "Ocurrió un error inesperado"}, status_code=500)


@app.get("/health", response_model=HealthResponse, tags=["Operación"], summary="Estado del servicio y del modelo")
def health(request: Request) -> JSONResponse:
    assistant = getattr(request.app.state, "assistant", None)
    body = HealthResponse(
        status="ok" if assistant else "degradado",
        modelo_cargado=assistant is not None,
        version=settings.app_version,
        entorno=settings.environment,
        modo_generacion=assistant.generator.mode if assistant else None,
        detalle=None if assistant else getattr(request.app.state, "load_error", None),
    )
    return JSONResponse(body.model_dump(), status_code=200 if assistant else 503)


app.include_router(router)

# Frontend estático: solo se publican los tres archivos conocidos (sin listar directorios).
FRONTEND_FILES = {"index.html": "text/html", "styles.css": "text/css", "app.js": "text/javascript"}

if settings.serve_frontend and settings.frontend_dir.is_dir():

    @app.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(settings.frontend_dir / "index.html", media_type="text/html")

    @app.get("/{asset}", include_in_schema=False)
    def frontend_asset(asset: str) -> FileResponse:
        if asset not in FRONTEND_FILES:
            raise StarletteHTTPException(404, "Recurso no encontrado")
        return FileResponse(settings.frontend_dir / asset, media_type=FRONTEND_FILES[asset])
