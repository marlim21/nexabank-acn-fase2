# Model card — `acn-intent-classifier` v1.0.0

## Archivos requeridos (`model/artifacts/`)

| Archivo | Contenido | Uso |
|---|---|---|
| `intent_classifier.joblib` | Pipeline de scikit-learn completo (vectorizadores TF-IDF + regresión logística). Incluye el preprocesamiento | Se carga una vez al iniciar el servicio |
| `model_metadata.json` | Versión, clases, versión de scikit-learn, semilla, **SHA-256 del modelo** y umbral de confianza | Verificación de integridad y configuración |
| `metrics.json` | Métricas de CV, test, análisis de confianza y recuperador | Las expone `/api/v1/model/info` y la consulta la validación |
| `confusion_matrix.csv` | Matriz de confusión en test | Análisis de errores |

La base de conocimiento (`data/knowledge_base/nexabank_kb.json`) es el índice del recuperador. No se entrena: se indexa
al iniciar el servicio.

**Compatibilidad:** el modelo se serializó con **scikit-learn 1.9.1** y debe servirse con la misma versión (fijada en
`requirements.txt`). Si la versión difiere, el servicio registra una advertencia. Si el hash no coincide, el modelo
**no se carga** y `/health` devuelve 503.

## Datos

- **Dataset sintético**, generado por `training/generate_dataset.py` (semilla 42): 10 motivos de contacto y
  22 frases núcleo por clase, combinadas con saludos, cierres, montos, comercios, fechas y ruido de chat (sin acentos o en
  minúsculas).
- **Partición sin fuga de información:** por cada clase, 4 frases núcleo se reservan exclusivamente para test. Así, el
  test (300 ejemplos) mide la generalización a redacciones **no vistas**. El entrenamiento usa 1,200 ejemplos.

## Entrenamiento

- Pipeline: `FeatureUnion(TF-IDF palabras 1–2 + TF-IDF caracteres 3–5)` → `LogisticRegression(class_weight="balanced")`.
- Selección de `C ∈ {0.5, 2, 8, 32}` con **StratifiedGroupKFold (5 folds, grupo = frase núcleo)** solo sobre el
  entrenamiento. Se eligió C = 0.5 (F1 macro en CV = 0.808 ± 0.076).
- Umbral de confianza = **0.30**: es el menor umbral cuyas predicciones *out-of-fold* alcanzan ≥ 90 % de exactitud. Se
  eligió sin usar el conjunto de prueba.

## Desempeño (conjunto de prueba independiente, n = 300)

| Métrica | Valor |
|---|---|
| Accuracy | **0.773** (línea base de clase mayoritaria: 0.100) |
| F1 macro / ponderado | 0.762 / 0.762 |
| Recall de clases sensibles (fraude + queja) | 0.850 |
| Cobertura con confianza ≥ 0.30 | 55.7 % de los casos, con accuracy de 0.916 |
| Accuracy con confianza < 0.30 | 0.594 (estos casos se marcan como `confianza_baja`) |

| Recuperador | Recall@1 | Recall@3 | MRR |
|---|---|---|---|
| Desarrollo (30 consultas), solo TF-IDF | 0.867 | 1.000 | 0.933 |
| Desarrollo, con pista del clasificador (pipeline real) | 0.967 | 1.000 | 0.983 |
| ***Holdout*** (22 consultas parafraseadas), con pista | **0.545** | **0.773** | 0.673 |

## Usos previstos y fuera de alcance

- **Previsto:** asistir a un agente humano con un borrador y una clasificación que el agente revisa.
- **Fuera de alcance:** decisiones automáticas, ejecutar transacciones, resolver fraude o quejas, o responder
  directamente al cliente.

## Limitaciones y sesgos conocidos

- Se entrenó con texto sintético: no refleja la diversidad real de clientes (regiones, edad, registro, errores
  ortográficos). Antes del piloto debe reentrenarse y validarse con transcripciones reales anonimizadas.
- Clases débiles: `credito_prestamo` (recall 0.43) y `tarjeta_credito` (F1 0.61). 8 de 30 casos de fraude se
  predicen como `aclaracion_cargo` (el riesgo se mitiga con revisión humana; ver el documento de validación).
- El recuperador léxico no reconoce sinónimos que no estén en la base de conocimiento.
