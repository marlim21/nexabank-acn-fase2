#!/usr/bin/env bash
# Despliegue del Asistente Cognitivo NexaBank en Azure Container Apps.
# PROCEDIMIENTO DOCUMENTADO — no ejecutado en el entregable de la Fase II.
# Requisitos: Azure CLI >= 2.60, sesión iniciada (az login) y permisos Contributor/Owner en la suscripción.
# Uso: bash deploy/azure/deploy_azure.sh    (desde la raíz del repositorio)
set -euo pipefail

# ---------- 1. Variables (ajústalas) ----------
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-nexabank-acn}"
LOCATION="${LOCATION:-eastus}"                     # verifica disponibilidad (sección 8.1 del manual)
ENVIRONMENT="${ENVIRONMENT:-cae-nexabank-acn}"
APP_NAME="${APP_NAME:-acn-api}"
ACR_NAME="${ACR_NAME:-acrnexabankacn$RANDOM}"      # único a nivel global, solo minúsculas y números
IDENTITY="${IDENTITY:-id-nexabank-acn}"
IMAGE_TAG="${IMAGE_TAG:-2.0.0}"
IMAGE="$ACR_NAME.azurecr.io/nexabank-acn:$IMAGE_TAG"

# ---------- 2. Preparación de la CLI ----------
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# ---------- 3. Grupo de recursos y registro de contenedores ----------
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"
az acr create --resource-group "$RESOURCE_GROUP" --location "$LOCATION" --name "$ACR_NAME" --sku Basic
az acr config authentication-as-arm update --registry "$ACR_NAME" --status enabled

# ---------- 4. Identidad administrada (extraer imágenes sin credenciales de administrador) ----------
az identity create --name "$IDENTITY" --resource-group "$RESOURCE_GROUP"
IDENTITY_ID=$(az identity show --name "$IDENTITY" --resource-group "$RESOURCE_GROUP" --query id --output tsv)

# ---------- 5. Construir y publicar la imagen ----------
# Opción A (sin Docker local): ACR construye la imagen en la nube a partir del Dockerfile.
az acr build --registry "$ACR_NAME" --image "nexabank-acn:$IMAGE_TAG" .
# Opción B (con Docker local):
#   docker build --platform linux/amd64 -t "$IMAGE" . && az acr login --name "$ACR_NAME" && docker push "$IMAGE"

# ---------- 6. Entorno de Container Apps (crea Log Analytics automáticamente) ----------
az containerapp env create --name "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" --location "$LOCATION"

# ---------- 7. Crear la aplicación ----------
# min/max replicas = 1: el KPI de adopción y los IDs de sugerencia viven en memoria (ver limitaciones).
az containerapp create \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENVIRONMENT" \
  --image "$IMAGE" \
  --target-port 8000 \
  --ingress external \
  --registry-server "$ACR_NAME.azurecr.io" \
  --user-assigned "$IDENTITY_ID" \
  --registry-identity "$IDENTITY_ID" \
  --cpu 0.5 --memory 1.0Gi \
  --min-replicas 1 --max-replicas 1 \
  --revision-suffix "v${IMAGE_TAG//./-}" \
  --env-vars ACN_ENV=azure ACN_LOG_LEVEL=INFO ACN_SERVE_FRONTEND=true ACN_WORKERS=1 \
  --query properties.configuration.ingress.fqdn --output tsv

FQDN=$(az containerapp show --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" --query properties.configuration.ingress.fqdn --output tsv)

# ---------- 8. CORS para el dominio público ----------
az containerapp update --name "$APP_NAME" --resource-group "$RESOURCE_GROUP" \
  --set-env-vars "ACN_CORS_ORIGINS=https://$FQDN"

# ---------- 9. Validación ----------
curl -fsS "https://$FQDN/health"
curl -fsS -X POST "https://$FQDN/api/v1/suggest" -H "Content-Type: application/json" \
  -d '{"mensaje":"Me robaron la tarjeta de débito","top_k":3}'
ACN_BASE_URL="https://$FQDN" python -m pytest tests/test_integration.py -v
echo "Aplicación disponible en: https://$FQDN"
