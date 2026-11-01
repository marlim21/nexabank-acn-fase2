"""Configuración del servicio mediante variables de entorno (sin secretos en el código)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "si", "sí"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "Asistente Cognitivo NexaBank (ACN)"
    app_version: str = os.getenv("ACN_APP_VERSION", "2.0.0")
    environment: str = os.getenv("ACN_ENV", "local")
    artifacts_dir: Path = Path(os.getenv("ACN_ARTIFACTS_DIR", PROJECT_ROOT / "model" / "artifacts"))
    kb_path: Path = Path(os.getenv("ACN_KB_PATH", PROJECT_ROOT / "data" / "knowledge_base" / "nexabank_kb.json"))
    frontend_dir: Path = Path(os.getenv("ACN_FRONTEND_DIR", PROJECT_ROOT / "frontend"))
    serve_frontend: bool = _bool("ACN_SERVE_FRONTEND", True)
    # Si no se define, se usa el umbral calibrado en entrenamiento (model_metadata.json).
    confidence_threshold: float | None = float(os.environ["ACN_CONFIDENCE_THRESHOLD"]) if os.getenv("ACN_CONFIDENCE_THRESHOLD") else None
    retrieval_min_score: float = float(os.getenv("ACN_RETRIEVAL_MIN_SCORE", "0.08"))
    top_k_default: int = int(os.getenv("ACN_TOP_K", "3"))
    max_text_chars: int = int(os.getenv("ACN_MAX_TEXT_CHARS", "2000"))
    max_turns: int = int(os.getenv("ACN_MAX_TURNS", "50"))
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("ACN_CORS_ORIGINS", "http://localhost:8080,http://localhost:8000").split(",") if o.strip()]
    )
    log_level: str = os.getenv("ACN_LOG_LEVEL", "INFO")
    # Generación con LLM: opcional. Solo se activa si hay ANTHROPIC_API_KEY y ACN_LLM_ENABLED no es false.
    llm_enabled: bool = _bool("ACN_LLM_ENABLED", True) and bool(os.getenv("ANTHROPIC_API_KEY"))
    llm_model: str = os.getenv("ACN_LLM_MODEL", "claude-opus-5-5")
    llm_timeout_s: float = float(os.getenv("ACN_LLM_TIMEOUT_S", "20"))


def get_settings() -> Settings:
    return Settings()
