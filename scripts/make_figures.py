"""Genera las figuras de evidencia del modelo a partir de model/artifacts/ (sin re-entrenar)."""

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "model" / "artifacts"
OUT = ROOT / "evidencias" / "modelo"
OUT.mkdir(parents=True, exist_ok=True)
INK, MUTED, GRID = "#17212f", "#5d6b7e", "#dbe1ea"
BLUE = LinearSegmentedColormap.from_list("seq", ["#ffffff", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
plt.rcParams.update({"font.size": 9, "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": GRID})

with (ART / "confusion_matrix.csv").open(encoding="utf-8") as fh:
    rows = list(csv.reader(fh))
labels, cm = rows[0][1:], [[int(v) for v in r[1:]] for r in rows[1:]]

fig, ax = plt.subplots(figsize=(7.5, 6.2))
ax.imshow(cm, cmap=BLUE, vmin=0, vmax=30)
ax.set_xticks(range(len(labels)), labels, rotation=40, ha="right")
ax.set_yticks(range(len(labels)), labels)
for i, row in enumerate(cm):
    for j, v in enumerate(row):
        if v:
            ax.text(j, i, v, ha="center", va="center", color="#ffffff" if v > 15 else INK, fontsize=8)
ax.set_xlabel("Predicho")
ax.set_ylabel("Real")
ax.set_title("Matriz de confusión — conjunto de prueba independiente (n=300)", loc="left", fontsize=10, color=INK)
for s in ax.spines.values():
    s.set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "matriz_confusion.png", dpi=170)

metrics = json.loads((ART / "metrics.json").read_text(encoding="utf-8"))
per = metrics["classifier"]["per_class"]
items = sorted(per.items(), key=lambda kv: kv[1]["f1-score"])
fig, ax = plt.subplots(figsize=(7.5, 4.4))
ax.barh([k for k, _ in items], [v["f1-score"] for _, v in items], color="#2a78d6", height=0.6)
for y, (_, v) in enumerate(items):
    ax.text(v["f1-score"] + 0.01, y, f'{v["f1-score"]:.2f}', va="center", fontsize=8, color=INK)
ax.axvline(0.70, color=MUTED, lw=1, ls="--")
ax.text(0.705, len(items) - 0.4, "criterio global 0.70", color=MUTED, fontsize=8)
ax.set_xlim(0, 1.08)
ax.set_xlabel("F1 por clase (test)")
ax.set_title("F1 por motivo de contacto — clasificador integrado", loc="left", fontsize=10, color=INK)
ax.grid(axis="x", color=GRID, lw=0.6)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "f1_por_clase.png", dpi=170)
print("ok", list(OUT.iterdir()))
