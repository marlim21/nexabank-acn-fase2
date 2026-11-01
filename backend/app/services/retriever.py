"""Recuperador del RAG: TF-IDF + similitud coseno sobre la base de conocimiento autorizada."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from app.services.preprocessing import normalize_text

CATEGORY_BOOST = 0.10  # refuerza artículos de la categoría que predijo el clasificador


@dataclass(frozen=True)
class Article:
    id: str
    category: str
    title: str
    content: str
    next_steps: list[str]
    customer_reply: str = ""
    keywords: str = ""


@dataclass(frozen=True)
class RetrievedArticle:
    article: Article
    score: float


def load_articles(kb_path: Path) -> list[Article]:
    data = json.loads(Path(kb_path).read_text(encoding="utf-8"))
    return [Article(a["id"], a["category"], a["title"], a["content"], list(a.get("next_steps", [])), a.get("customer_reply", ""), a.get("keywords", "")) for a in data["articles"]]


class KnowledgeBaseRetriever:
    def __init__(self, articles: list[Article]):
        if not articles:
            raise ValueError("La base de conocimiento está vacía")
        self.articles = articles
        # Título (con doble peso), palabras clave/sinónimos curados y contenido del artículo.
        corpus = [f"{a.title} {a.title} {a.keywords} {a.content}" for a in articles]
        self.vectorizer = TfidfVectorizer(preprocessor=normalize_text, ngram_range=(1, 2), sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query: str, top_k: int = 3, category_hint: str | None = None, min_score: float = 0.0) -> list[RetrievedArticle]:
        q = self.vectorizer.transform([query])
        scores = linear_kernel(q, self.matrix).ravel()
        if category_hint:
            scores = scores + np.array([CATEGORY_BOOST if a.category == category_hint else 0.0 for a in self.articles])
        order = np.argsort(-scores)[:top_k]
        return [RetrievedArticle(self.articles[i], round(float(scores[i]), 4)) for i in order if scores[i] > min_score]
