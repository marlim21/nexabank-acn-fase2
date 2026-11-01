# Contrato de la API REST — Asistente Cognitivo NexaBank v2.0.0

- **URL base local:** `http://localhost:8000` (imagen única) o `http://localhost:8080` (vía frontend nginx).
- **Formato:** JSON UTF-8 (`Content-Type: application/json`).
- **Documentación interactiva:** `GET /docs` (Swagger UI) y `GET /openapi.json` (OpenAPI 3).
- **Trazabilidad:** cada respuesta incluye la cabecera `X-Request-ID`. Si el cliente la envía, se respeta su valor.
- **Privacidad:** los logs registran solo metadatos (ruta, código, latencia, motivo detectado), nunca el texto del cliente.

Todos los ejemplos de respuesta de este documento son **salidas reales** del contenedor, guardadas en
`evidencias/api/`.

## Reglas de validación comunes

| Regla | Comportamiento |
|---|---|
| Campos desconocidos | Se rechazan con **422** (`extra="forbid"`) |
| Tipos estrictos | `"3"` no se acepta como entero ni `123` como texto (**422**) |
| Texto vacío o solo espacios | **422** |
| Longitud de texto | De 3 a 2,000 caracteres (`ACN_MAX_TEXT_CHARS`) |
| Cuerpo de la solicitud | Máximo 64 KB; si se excede, la respuesta es **413** |
| JSON malformado | **422** |
| Errores | Nunca devuelven el valor recibido, para no reflejar datos sensibles |

## Formato de error

```json
{"error": "datos_invalidos", "detalle": [{"campo": "mensaje", "error": "String should have at least 3 characters"}]}
```

| Código HTTP | `error` | Cuándo ocurre |
|---|---|---|
| 404 | `no_encontrado` | La ruta no existe o el `id_sugerencia` es desconocido |
| 405 | `metodo_no_permitido` | Se usó un método HTTP incorrecto (por ejemplo `GET /api/v1/suggest`) |
| 413 | `solicitud_demasiado_grande` | El cuerpo pesa más de 64 KB |
| 422 | `datos_invalidos` | Falla la validación de esquema, tipos o rangos |
| 500 | `error_interno` | Error no controlado (el detalle se registra en el log, no se expone) |
| 503 | `modelo_no_disponible` | El modelo o sus archivos no cargaron (falta un archivo, el hash no coincide o la base de conocimiento no existe) |

---

## GET `/health`

Indica el estado del servicio y del modelo. Lo usan el `HEALTHCHECK` de Docker y las sondas de la nube.

**200 OK** (`evidencias/api/01_health.txt`):

```json
{"status":"ok","modelo_cargado":true,"version":"2.0.0","entorno":"docker","modo_generacion":"extractivo","detalle":null}
```

**503** cuando el modelo no cargó: `{"status":"degradado","modelo_cargado":false,...,"detalle":"El hash del artefacto no coincide con model_metadata.json"}`.

---

## POST `/api/v1/suggest`

Sugerencia de respuesta con RAG para el agente.

**Solicitud**

| Campo | Tipo | Requerido | Restricciones | Descripción |
|---|---|---|---|---|
| `mensaje` | string | sí | 3–2,000 caracteres, no vacío | Mensaje del cliente |
| `top_k` | integer | no (3) | 1–5 | Número máximo de artículos a recuperar |

```json
{"mensaje": "No reconozco un cargo de 1,200 pesos en Amazon de ayer", "top_k": 3}
```

**Respuesta 200** (`evidencias/api/02_suggest_aclaracion.json`):

```json
{
  "id_sugerencia": "3d0e2ace-8ea3-41e0-b6bf-45beb357c463",
  "motivo": {
    "intent": "aclaracion_cargo", "etiqueta": "Aclaración de cargo", "confianza": 0.8448,
    "alternativas": [{"intent": "credito_prestamo", "confianza": 0.0242}, {"intent": "banca_digital", "confianza": 0.0205}],
    "sensible": false, "confianza_baja": false
  },
  "sugerencia": "Gracias por comunicarse con NexaBank. Lamento la situación. Voy a registrar una aclaración por el cargo que no reconoce; ...",
  "modo_generacion": "extractivo",
  "fuentes": [
    {"id": "KB-003", "titulo": "Aclaración de cargos no reconocidos", "categoria": "aclaracion_cargo", "score": 0.2905},
    {"id": "KB-004", "titulo": "Cobros duplicados y comisiones no reconocidas", "categoria": "aclaracion_cargo", "score": 0.2195}
  ],
  "acciones_sugeridas": ["Registrar folio de aclaración con fecha, monto y comercio", "Informar el plazo de respuesta de 45 días naturales", "Evaluar si procede abono provisional"],
  "escalamiento_requerido": false,
  "requiere_aprobacion_humana": true,
  "mensaje_enmascarado": "No reconozco un cargo de 1,200 pesos en Amazon de ayer",
  "latencia_ms": 2.9
}
```

| Campo | Significado |
|---|---|
| `motivo.confianza` | Probabilidad de la clase predicha (regresión logística) |
| `motivo.confianza_baja` | `true` si `confianza` < umbral (0.30, calibrado *out-of-fold* en el entrenamiento) |
| `motivo.sensible` / `escalamiento_requerido` | `true` para `posible_fraude` y `queja_servicio`: la IA no los resuelve sola |
| `fuentes` | **Hasta** `top_k` artículos con `score` > 0.08 (`ACN_RETRIEVAL_MIN_SCORE`); puede devolver menos |
| `modo_generacion` | `extractivo`, `llm`, o `extractivo_fallback` (el LLM falló y se usó el modo extractivo) |
| `mensaje_enmascarado` | Texto realmente procesado: tarjeta, CLABE, correo, teléfono y NIP aparecen como `[TARJETA]`, `[CLABE]`, etc. |

---

## POST `/api/v1/classify`

Solo la clasificación del motivo.

```json
// Solicitud
{"texto": "Olvidé mi contraseña de la app"}
// Respuesta 200 (evidencias/api/04_classify.json)
{"intent": "banca_digital", "etiqueta": "Banca digital y acceso", "confianza": 0.8051,
 "alternativas": [{"intent": "bloqueo_tarjeta", "confianza": 0.028}, {"intent": "posible_fraude", "confianza": 0.0251}],
 "sensible": false, "confianza_baja": false}
```

Las 10 clases posibles son: `consulta_saldo`, `aclaracion_cargo`, `bloqueo_tarjeta`, `posible_fraude`, `transferencias`,
`credito_prestamo`, `tarjeta_credito`, `actualizacion_datos`, `banca_digital` y `queja_servicio`.

---

## POST `/api/v1/summarize`

Resumen del caso para el CRM. Requiere aprobación humana antes de guardarse.

| Campo | Tipo | Restricciones |
|---|---|---|
| `turnos` | array | De 1 a 50 elementos; debe incluir al menos un turno del `cliente` |
| `turnos[].rol` | `"cliente"` \| `"agente"` | Cualquier otro valor da 422 |
| `turnos[].texto` | string | 1–2,000 caracteres, no vacío |

```json
// Solicitud
{"turnos": [
  {"rol": "cliente", "texto": "Me cobraron dos veces 899 pesos en Netflix el 3 de octubre."},
  {"rol": "agente", "texto": "Registré la aclaración con folio 55821."}
]}
// Respuesta 200 (evidencias/api/05_summarize.json)
{
  "motivo": {"intent": "aclaracion_cargo", "etiqueta": "Aclaración de cargo", "confianza": 0.3149, "...": "..."},
  "resumen": "Motivo de contacto: Aclaración de cargo. El cliente indica: Me cobraron dos veces 899 pesos en Netflix el 3 de octubre. Última acción del agente: Registré la aclaración con folio 55821.",
  "entidades": {"montos": ["899 pesos"], "fechas": ["3 de octubre"]},
  "acciones_sugeridas": ["Verificar si el cargo está liquidado o pendiente", "Levantar aclaración si el cargo ya fue liquidado"],
  "fuente": "KB-004",
  "escalamiento_requerido": false,
  "requiere_aprobacion_humana": true,
  "turnos_procesados": 2
}
```

---

## POST `/api/v1/feedback`

Registra la decisión del agente sobre una sugerencia (*human-in-the-loop*). Alimenta el KPI de adopción.

```json
// Solicitud
{"id_sugerencia": "3d0e2ace-8ea3-41e0-b6bf-45beb357c463", "decision": "aprobada"}   // aprobada | editada | rechazada
// Respuesta 200
{"registrado": true, "estadisticas": {"total": 1, "aprobada": 1, "editada": 0, "rechazada": 0, "tasa_aceptacion": 1.0, "tasa_edicion": 0.0, "tasa_rechazo": 0.0}}
```

Si el `id_sugerencia` no fue emitido por esta instancia, la respuesta es **404**.

## GET `/api/v1/metrics/adoption`

Devuelve las mismas `estadisticas` acumuladas. Las cuentas son por instancia y se reinician con el contenedor
(ver limitaciones).

## GET `/api/v1/model/info`

Devuelve el nombre, la versión, la fecha de entrenamiento, el algoritmo, las clases, el modo de generación, el umbral,
las métricas de test y las métricas del recuperador (`evidencias/api/07_model_info.json`).

---

## Variables de entorno

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `PORT` | 8000 | Puerto de escucha dentro del contenedor |
| `ACN_ENV` | local | Nombre del entorno que reporta `/health` |
| `ACN_LOG_LEVEL` | INFO | Nivel de log |
| `ACN_TOP_K` | 3 | Valor por defecto de `top_k` |
| `ACN_MAX_TEXT_CHARS` | 2000 | Longitud máxima de texto |
| `ACN_CONFIDENCE_THRESHOLD` | *(vacío → 0.30 de metadatos)* | Umbral de `confianza_baja` |
| `ACN_RETRIEVAL_MIN_SCORE` | 0.08 | Score mínimo para devolver un artículo |
| `ACN_CORS_ORIGINS` | `http://localhost:8080,http://localhost:8000` | Orígenes permitidos (CORS) |
| `ACN_SERVE_FRONTEND` | true | Si la API también sirve la consola web |
| `ACN_WORKERS` | 1 | Procesos de Uvicorn (ver la limitación de estado en memoria) |
| `ACN_ARTIFACTS_DIR` / `ACN_KB_PATH` | rutas del repositorio | Ubicación del modelo y de la base de conocimiento |
| `ANTHROPIC_API_KEY` | *(vacío)* | **Secreto.** Si se define, se activa la generación con Claude |
| `ACN_LLM_ENABLED` / `ACN_LLM_MODEL` / `ACN_LLM_TIMEOUT_S` | true / `claude-opus-5-5` / 20 | Configuración del LLM opcional |
