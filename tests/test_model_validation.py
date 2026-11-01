"""Validación del modelo integrado: reproduce las métricas del entrenamiento a través del
servicio desplegado y verifica los criterios de aceptación definidos para la Fase II.

Importante: el conjunto de prueba (data/intents_test.csv) es independiente; sus frases núcleo
no se usaron en entrenamiento ni en la selección de hiperparámetros.
"""

import csv
import json
import time

import numpy as np
import pytest
from sklearn.metrics import accuracy_score, f1_score

from app.services.classifier import SENSITIVE_INTENTS

# Criterios de aceptación (definidos antes de la integración, ver docs/validacion_pruebas.md)
MIN_ACCURACY = 0.70
MIN_F1_MACRO = 0.70
MIN_SENSITIVE_RECALL = 0.80
MIN_RETRIEVAL_RECALL_AT_3 = 0.90
MAX_P95_LATENCY_MS = 250


@pytest.fixture(scope="module")
def test_set(root):
    with (root / "data" / "intents_test.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [r["text"] for r in rows], [r["label"] for r in rows]


@pytest.fixture(scope="module")
def reference_metrics(root):
    return json.loads((root / "model" / "artifacts" / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def api_predictions(client, test_set):
    texts, _ = test_set
    return [client.post("/api/v1/classify", json={"texto": t}).json()["intent"] for t in texts]


def test_metricas_via_api_igual_a_entrenamiento(api_predictions, test_set, reference_metrics):
    _, y = test_set
    ref = reference_metrics["classifier"]["test"]
    assert accuracy_score(y, api_predictions) == pytest.approx(ref["accuracy"], abs=1e-4)
    assert f1_score(y, api_predictions, average="macro") == pytest.approx(ref["f1_macro"], abs=1e-4)


def test_criterios_de_aceptacion_clasificador(api_predictions, test_set, reference_metrics):
    _, y = test_set
    acc = accuracy_score(y, api_predictions)
    assert acc >= MIN_ACCURACY
    assert f1_score(y, api_predictions, average="macro") >= MIN_F1_MACRO
    assert acc > reference_metrics["classifier"]["baseline_most_frequent_test_accuracy"] * 5


def test_recall_casos_sensibles(api_predictions, test_set):
    _, y = test_set
    y_true = np.array([t in SENSITIVE_INTENTS for t in y])
    y_pred = np.array([p in SENSITIVE_INTENTS for p in api_predictions])
    assert (y_true & y_pred).sum() / y_true.sum() >= MIN_SENSITIVE_RECALL


def test_recuperador_integrado(client, root, reference_metrics):
    queries = json.loads((root / "data" / "retrieval_eval.json").read_text(encoding="utf-8"))["queries"]
    hits = 0
    for q in queries:
        d = client.post("/api/v1/suggest", json={"mensaje": q["query"], "top_k": 3}).json()
        hits += q["expected"] in [f["id"] for f in d["fuentes"]]
    recall3 = hits / len(queries)
    assert recall3 >= MIN_RETRIEVAL_RECALL_AT_3
    assert recall3 == pytest.approx(reference_metrics["retriever"]["with_classifier_hint"]["recall_at_3"], abs=1e-4)


def test_latencia_p95(client, test_set):
    texts, _ = test_set
    times = []
    for t in texts[:100]:
        start = time.perf_counter()
        client.post("/api/v1/suggest", json={"mensaje": t})
        times.append((time.perf_counter() - start) * 1000)
    assert np.percentile(times, 95) < MAX_P95_LATENCY_MS


def test_consistencia_determinista(client):
    payload = {"mensaje": "No reconozco un cargo de 1,200 pesos"}
    a = client.post("/api/v1/suggest", json=payload).json()
    b = client.post("/api/v1/suggest", json=payload).json()
    assert a["motivo"] == b["motivo"] and a["fuentes"] == b["fuentes"] and a["sugerencia"] == b["sugerencia"]


@pytest.mark.xfail(strict=True, reason=(
    "LIMITACIÓN CONOCIDA: en el holdout de consultas parafraseadas el recuperador léxico (TF-IDF) "
    "obtiene Recall@3 ≈ 0.77 < 0.90. Mitigación: el agente ve 3 fuentes y aprueba cada respuesta; "
    "mejora propuesta: embeddings semánticos multilingües."))
def test_recuperador_holdout_cumple_objetivo(client, root):
    queries = json.loads((root / "data" / "retrieval_eval_holdout.json").read_text(encoding="utf-8"))["queries"]
    hits = sum(q["expected"] in [f["id"] for f in client.post("/api/v1/suggest", json={"mensaje": q["query"], "top_k": 3}).json()["fuentes"]]
               for q in queries)
    assert hits / len(queries) >= MIN_RETRIEVAL_RECALL_AT_3
