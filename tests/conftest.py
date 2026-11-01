"""Configuración común de pytest: rutas, cliente de pruebas y utilidades."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.assistant import ACNAssistant  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # El context manager ejecuta el "lifespan": el modelo se carga una vez por sesión de pruebas.
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def assistant() -> ACNAssistant:
    return ACNAssistant(get_settings())


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT
