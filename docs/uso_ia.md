# Uso de herramientas de IA en el desarrollo de la Fase II

## Herramienta utilizada

| Herramienta | Proveedor / modelo | Modo de uso |
|---|---|---|
| **Claude Code** (aplicación de escritorio) | Anthropic · Claude Opus 5.5 | Asistente de ingeniería con acceso al sistema de archivos y a la terminal del equipo del autor: leyó los entregables de la Fase I, escribió código, ejecutó comandos (Python, Docker, pytest) y redactó la documentación |

**No se usó GitHub Copilot.** En esta fase no se atribuyen acciones a otras herramientas.

## Actividades en las que participó la IA

| # | Actividad | Instrucción (resumen del prompt) | Resultado obtenido | Validación |
|---|---|---|---|---|
| 1 | Diagnóstico de la Fase I | "Analiza los archivos de la Fase I, identifica el modelo construido, qué es reutilizable y qué falta" (prompt maestro de la Fase II) | Diagnóstico: la Fase I es un *business case* sin modelo, dataset ni código. El diagnóstico se presentó **antes** de construir | El autor eligió entre las alternativas propuestas: RAG + clasificador, LLM opcional, Colima y repositorio público |
| 2 | Datos sintéticos | Construir un corpus coherente con la Fase I, etiquetado como sintético | `generate_dataset.py`, base de conocimiento de 22 artículos y conjuntos de evaluación | Partición sin fuga de información y revisión del contenido de la base de conocimiento |
| 3 | Modelo y evaluación | Entrenar y evaluar sin fuga, reportando métricas reales | `train.py`, CV agrupada, umbral *out-of-fold* y *holdout* del recuperador | Se detectaron y corrigieron E-01 y E-02; los resultados desfavorables (*holdout* 0.77) se reportan, no se ocultan |
| 4 | Backend, API y frontend | Implementar la API REST, la validación, el manejo de errores y la consola web | `backend/app/*`, `frontend/*` | 100 pruebas automatizadas; inspección visual de capturas (E-03, E-07) |
| 5 | Contenerización | Dockerfile, Compose, nginx y *healthchecks* | Imagen única + Compose de 2 servicios | Ejecución real en Docker y pruebas de integración y E2E contra los contenedores (E-06, E-09) |
| 6 | Pruebas | Plan de pruebas unitarias, funcionales, de casos extremos, de integración y E2E | `tests/*`, `scripts/validate_docker.sh` | Se ejecutaron y se guardó la salida real en `evidencias/` |
| 7 | Manual de despliegue | Comparar opciones cloud y documentar Azure con fuentes oficiales | `docs/manual_despliegue.md`, `deploy/azure/deploy_azure.sh` | Los comandos se contrastaron con Microsoft Learn (consultado el 1 de noviembre de 2026). **El despliegue no se ejecutó** |
| 8 | Documentación | README, arquitectura, API, *model card* y validación | `docs/*`, `README.md` | Las cifras se tomaron de los archivos de evidencia, no se escribieron de memoria |

## Ejemplos de instrucciones dentro del proceso

- "No inventes modelos entrenados, resultados, métricas, archivos, endpoints, pruebas ni evidencias. Distingue entre
  información comprobada, inferida, propuesta y pendiente." (regla del prompt maestro, aplicada en todo el proyecto)
- "No consideres exitosa la contenerización únicamente porque la imagen se construya: debe demostrarse que la
  aplicación funciona dentro del contenedor." Esta regla motivó las pruebas de integración contra los contenedores,
  donde apareció el defecto E-06.
- "Distingue entre un despliegue real ejecutado y un procedimiento documentado para despliegue futuro." Por eso el
  manual se declara como no ejecutado.

## Validación humana pendiente del autor

La IA generó y ejecutó el código y las pruebas. Antes de entregar, **el autor debe**:

1. Revisar el contenido de la base de conocimiento sintética (`data/knowledge_base/nexabank_kb.json`).
2. Ejecutar personalmente `bash scripts/validate_docker.sh` y abrir <http://localhost:8080> para comprobar el flujo.
3. Revisar que el repositorio público no contenga datos personales ni secretos (`git ls-files`).
4. Leer los dos documentos PDF y confirmar que reflejan su criterio académico.
