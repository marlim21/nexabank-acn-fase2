"""Entrena y evalúa los componentes de ML del Asistente Cognitivo NexaBank.

1. Clasificador del motivo de contacto (TF-IDF + Regresión Logística):
   - validación cruzada estratificada (5 folds) sobre entrenamiento,
   - evaluación final sobre el conjunto de prueba independiente (frases núcleo no vistas),
   - comparación contra una línea base (clase más frecuente).
2. Recuperador RAG (TF-IDF + coseno): Recall@1, Recall@3 y MRR sobre data/retrieval_eval.json.

Uso (desde la raíz del repositorio):
    PYTHONPATH=backend python training/train.py
Salida: model/artifacts/{intent_classifier.joblib, model_metadata.json, metrics.json, confusion_matrix.csv}
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict, cross_validate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.classifier import SENSITIVE_INTENTS, build_pipeline  # noqa: E402
from app.services.retriever import KnowledgeBaseRetriever, load_articles  # noqa: E402

SEED = 42
DATA = ROOT / "data"
ARTIFACTS = ROOT / "model" / "artifacts"
MODEL_VERSION = "1.0.0"
C_GRID = [0.5, 2.0, 8.0, 32.0]
THRESHOLD_GRID = [round(x, 2) for x in np.arange(0.10, 0.91, 0.05)]
TARGET_PRECISION = 0.90


def read_csv(path: Path) -> tuple[list[str], list[str], list[str]]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [r["text"] for r in rows], [r["label"] for r in rows], [r["core_id"] for r in rows]


def evaluate_retriever(retriever: KnowledgeBaseRetriever, eval_path: Path, classifier=None) -> dict:
    queries = json.loads(eval_path.read_text(encoding="utf-8"))["queries"]
    hits1 = hits3 = 0
    rr = []
    for q in queries:
        hint = classifier.predict([q["query"]])[0] if classifier is not None else None
        ids = [r.article.id for r in retriever.search(q["query"], top_k=len(retriever.articles), category_hint=hint)]
        rank = ids.index(q["expected"]) + 1 if q["expected"] in ids else None
        hits1 += rank == 1
        hits3 += rank is not None and rank <= 3
        rr.append(1 / rank if rank else 0.0)
    n = len(queries)
    return {"n_queries": n, "recall_at_1": round(hits1 / n, 4), "recall_at_3": round(hits3 / n, 4), "mrr": round(float(np.mean(rr)), 4)}


def main() -> None:
    X_train, y_train, groups = read_csv(DATA / "intents_train.csv")
    X_test, y_test, _ = read_csv(DATA / "intents_test.csv")
    labels = sorted(set(y_train))

    # 1) Selección de hiperparámetros SOLO con validación cruzada agrupada por frase núcleo
    #    (StratifiedGroupKFold): una misma frase núcleo nunca queda en train y validación a la vez.
    #    El conjunto de prueba no se usa en esta etapa.
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
    search = []
    for c in C_GRID:
        res = cross_validate(build_pipeline(SEED, C=c), X_train, y_train, groups=groups, cv=cv, scoring=["accuracy", "f1_macro"])
        search.append({"C": c, "accuracy_mean": round(float(res["test_accuracy"].mean()), 4),
                       "accuracy_std": round(float(res["test_accuracy"].std()), 4),
                       "f1_macro_mean": round(float(res["test_f1_macro"].mean()), 4),
                       "f1_macro_std": round(float(res["test_f1_macro"].std()), 4)})
    best = max(search, key=lambda r: r["f1_macro_mean"])

    # 1b) Umbral de confianza: se elige con predicciones out-of-fold (sin tocar test) como el menor
    #     umbral cuyas predicciones "confiables" alcanzan >= TARGET_PRECISION de exactitud.
    oof = cross_val_predict(build_pipeline(SEED, C=best["C"]), X_train, y_train, groups=groups, cv=cv, method="predict_proba")
    oof_classes = np.array(sorted(set(y_train)))
    oof_conf, oof_ok = oof.max(axis=1), oof_classes[oof.argmax(axis=1)] == np.array(y_train)
    threshold = next((t for t in THRESHOLD_GRID if oof_ok[oof_conf >= t].mean() >= TARGET_PRECISION), THRESHOLD_GRID[-1])

    # 2) Entrenamiento final con el mejor C y evaluación en el conjunto de prueba independiente
    model = build_pipeline(SEED, C=best["C"]).fit(X_train, y_train)
    y_pred = model.predict(X_test)
    proba = model.predict_proba(X_test)
    baseline = DummyClassifier(strategy="most_frequent").fit(X_train, y_train)

    sensitive_true = np.array([y in SENSITIVE_INTENTS for y in y_test])
    sensitive_pred = np.array([y in SENSITIVE_INTENTS for y in y_pred])
    report = classification_report(y_test, y_pred, labels=labels, output_dict=True, zero_division=0)

    conf_test = proba.max(axis=1)
    ok_test = y_pred == np.array(y_test)
    confidence_analysis = {
        "threshold_selected_oof": threshold,
        "target_precision": TARGET_PRECISION,
        "test_coverage_above_threshold": round(float((conf_test >= threshold).mean()), 4),
        "test_accuracy_above_threshold": round(float(ok_test[conf_test >= threshold].mean()), 4),
        "test_accuracy_below_threshold": round(float(ok_test[conf_test < threshold].mean()), 4) if (conf_test < threshold).any() else None,
    }

    # 3) Recuperador RAG: solo (TF-IDF) e integrado (con la categoría predicha por el clasificador)
    retriever = KnowledgeBaseRetriever(load_articles(DATA / "knowledge_base" / "nexabank_kb.json"))
    retrieval = {
        "standalone": evaluate_retriever(retriever, DATA / "retrieval_eval.json"),
        "with_classifier_hint": evaluate_retriever(retriever, DATA / "retrieval_eval.json", classifier=model),
        # Holdout redactado después del ajuste de palabras clave: estimación sin sesgo.
        "holdout_standalone": evaluate_retriever(retriever, DATA / "retrieval_eval_holdout.json"),
        "holdout_with_classifier_hint": evaluate_retriever(retriever, DATA / "retrieval_eval_holdout.json", classifier=model),
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    model_path = ARTIFACTS / "intent_classifier.joblib"
    joblib.dump(model, model_path, compress=3)
    sha = hashlib.sha256(model_path.read_bytes()).hexdigest()

    metrics = {
        "classifier": {
            "cross_validation_train": {"folds": 5, "strategy": "StratifiedGroupKFold (grupo = frase núcleo)", "selected_C": best["C"], **{k: v for k, v in best.items() if k != "C"}},
            "hyperparameter_search": search,
            "test": {
                "n": len(y_test),
                "accuracy": round(accuracy_score(y_test, y_pred), 4),
                "f1_macro": round(f1_score(y_test, y_pred, average="macro"), 4),
                "f1_weighted": round(f1_score(y_test, y_pred, average="weighted"), 4),
                "mean_confidence": round(float(proba.max(axis=1).mean()), 4),
                "sensitive_recall": round(float((sensitive_pred & sensitive_true).sum() / sensitive_true.sum()), 4),
            },
            "confidence_analysis": confidence_analysis,
            "baseline_most_frequent_test_accuracy": round(accuracy_score(y_test, baseline.predict(X_test)), 4),
            "per_class": {k: {m: round(v, 4) for m, v in report[k].items()} for k in labels},
        },
        "retriever": retrieval,
    }
    metadata = {
        "model_name": "acn-intent-classifier",
        "model_version": MODEL_VERSION,
        "algorithm": f"FeatureUnion(TF-IDF palabras 1-2 + TF-IDF caracteres 3-5) -> LogisticRegression(C={best['C']}, balanced)",
        "classes": list(model.classes_),
        "sensitive_intents": sorted(SENSITIVE_INTENTS),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "seed": SEED,
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "classifier_sha256": sha,
        "confidence_threshold": threshold,
        "data_note": "Datos sintéticos generados por training/generate_dataset.py (NexaBank es ficticia).",
    }
    (ARTIFACTS / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    (ARTIFACTS / "model_metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    cm = confusion_matrix(y_test, y_pred, labels=labels)
    with (ARTIFACTS / "confusion_matrix.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["real\\predicho", *labels])
        writer.writerows([[lab, *row] for lab, row in zip(labels, cm.tolist())])

    print(json.dumps({"cv": metrics["classifier"]["cross_validation_train"], "test": metrics["classifier"]["test"], "confidence": confidence_analysis,
                      "baseline": metrics["classifier"]["baseline_most_frequent_test_accuracy"], "retriever": retrieval}, indent=2))


if __name__ == "__main__":
    main()
