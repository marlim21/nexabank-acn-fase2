#!/usr/bin/env bash
# Valida la contenerización de punta a punta y guarda las evidencias en evidencias/.
#   1) Imagen única (API + modelo + frontend): build, run, healthcheck, endpoints, pruebas de integración.
#   2) docker compose (frontend nginx + API): build, up, pruebas de integración y E2E vía el frontend.
# Uso: bash scripts/validate_docker.sh   (desde la raíz del repositorio, con Docker en ejecución)
set -euo pipefail
cd "$(dirname "$0")/.."
EV=evidencias
mkdir -p "$EV/docker" "$EV/api" "$EV/frontend_backend" "$EV/pruebas"
PY=${PYTHON:-.venv/bin/python}
IMAGE=nexabank-acn:2.0.0

wait_healthy() {  # $1 = contenedor
  for _ in $(seq 1 30); do
    status=$(docker inspect --format '{{.State.Health.Status}}' "$1" 2>/dev/null || echo "none")
    [ "$status" = "healthy" ] && return 0
    sleep 2
  done
  echo "El contenedor $1 no llegó a estado healthy" >&2; docker logs "$1" >&2; return 1
}

echo "== 1. Imagen única =="
{ echo "\$ docker build -t $IMAGE ."; docker build -t "$IMAGE" . 2>&1; } > "$EV/docker/01_docker_build.log"
docker image ls "$IMAGE" > "$EV/docker/02_docker_image.txt"
docker rm -f acn-single >/dev/null 2>&1 || true
docker run -d --name acn-single -p 8000:8000 "$IMAGE" > /dev/null
wait_healthy acn-single
{ echo "\$ docker ps"; docker ps --filter name=acn-single --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'; } > "$EV/docker/03_docker_run_ps.txt"

curl -s -i http://localhost:8000/health > "$EV/api/01_health.txt"
curl -s -X POST http://localhost:8000/api/v1/suggest -H 'Content-Type: application/json' \
  -d '{"mensaje":"No reconozco un cargo de 1,200 pesos en Amazon de ayer","top_k":3}' | $PY -m json.tool --no-ensure-ascii > "$EV/api/02_suggest_aclaracion.json"
curl -s -X POST http://localhost:8000/api/v1/suggest -H 'Content-Type: application/json' \
  -d '{"mensaje":"Me llamaron del banco y les di mi NIP, mi tarjeta es 4152 3134 5678 9012"}' | $PY -m json.tool --no-ensure-ascii > "$EV/api/03_suggest_fraude_escalamiento.json"
curl -s -X POST http://localhost:8000/api/v1/classify -H 'Content-Type: application/json' \
  -d '{"texto":"Olvidé mi contraseña de la app"}' | $PY -m json.tool --no-ensure-ascii > "$EV/api/04_classify.json"
curl -s -X POST http://localhost:8000/api/v1/summarize -H 'Content-Type: application/json' \
  -d '{"turnos":[{"rol":"cliente","texto":"Me cobraron dos veces 899 pesos en Netflix el 3 de octubre."},{"rol":"agente","texto":"Registré la aclaración con folio 55821."}]}' \
  | $PY -m json.tool --no-ensure-ascii > "$EV/api/05_summarize.json"
curl -s -i -X POST http://localhost:8000/api/v1/suggest -H 'Content-Type: application/json' -d '{"mensaje":""}' > "$EV/api/06_error_422_mensaje_vacio.txt"
curl -s http://localhost:8000/api/v1/model/info | $PY -m json.tool --no-ensure-ascii > "$EV/api/07_model_info.json"
curl -s http://localhost:8000/openapi.json | $PY -m json.tool --no-ensure-ascii > "$EV/api/08_openapi.json"
ACN_BASE_URL=http://localhost:8000 $PY -m pytest tests/test_integration.py -v -p no:cacheprovider > "$EV/pruebas/02_integracion_imagen_unica.txt" 2>&1
docker logs acn-single > "$EV/docker/04_logs_contenedor_api.txt" 2>&1
docker rm -f acn-single > /dev/null

echo "== 2. docker compose (frontend + API) =="
{ echo "\$ docker compose up -d --build"; docker compose up -d --build 2>&1; } > "$EV/docker/05_compose_up.log"
wait_healthy acn-api
wait_healthy acn-frontend
{ echo "\$ docker compose ps"; docker compose ps; } > "$EV/docker/06_compose_ps.txt"
ACN_BASE_URL=http://localhost:8080 $PY -m pytest tests/test_integration.py -v -p no:cacheprovider > "$EV/pruebas/03_integracion_compose_via_frontend.txt" 2>&1
ACN_FRONTEND_URL=http://localhost:8080 $PY -m pytest tests/e2e -v -p no:cacheprovider > "$EV/pruebas/04_e2e_navegador.txt" 2>&1
echo "== 3. Caso extremo: backend detenido =="
docker compose stop api > /dev/null 2>&1
$PY scripts/check_backend_down.py http://localhost:8080 > "$EV/pruebas/06_frontend_backend_detenido.txt" 2>&1 \
  || echo "X-19 FALLIDO (ver $EV/pruebas/06_frontend_backend_detenido.txt)"
docker compose start api > /dev/null 2>&1   # siempre se restablece la API
wait_healthy acn-api
docker compose logs --no-color > "$EV/docker/07_compose_logs.txt" 2>&1
echo "Contenedores en ejecución: frontend http://localhost:8080 · API http://localhost:8000/docs"
echo "Para detenerlos: docker compose down"
tail -n 1 "$EV"/pruebas/*.txt
