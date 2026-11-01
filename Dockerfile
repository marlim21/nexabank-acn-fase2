# Imagen del Asistente Cognitivo NexaBank (API FastAPI + modelo + frontend estático).
# Una sola imagen facilita el despliegue en servicios de contenedores administrados (p. ej. Azure Container Apps).
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend \
    PORT=8000 \
    ACN_ENV=docker \
    ACN_SERVE_FRONTEND=true

WORKDIR /app

# 1) Dependencias primero (aprovecha la caché de capas de Docker)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2) Código, modelo entrenado, base de conocimiento y frontend
COPY backend/ backend/
COPY model/artifacts/ model/artifacts/
COPY data/knowledge_base/ data/knowledge_base/
COPY frontend/ frontend/

# 3) Usuario sin privilegios (buena práctica de seguridad)
RUN useradd --create-home --uid 10001 acn && chown -R acn:acn /app
USER acn

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4).status == 200 else 1)"

# PORT es configurable (los servicios cloud lo inyectan). 1 worker por contenedor: el estado de sugerencias
# y el KPI de adopción viven en memoria del proceso; se escala horizontalmente con réplicas.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${ACN_WORKERS:-1} --proxy-headers"]
