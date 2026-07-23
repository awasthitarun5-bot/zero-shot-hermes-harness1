"""tests/unit/test_api.py — Phase-1 compile checks only (no real HTTP)."""
from __future__ import annotations

from pathlib import Path

from src.api import create_app


_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_create_app_imports() -> None:
    app = create_app()
    assert app is not None


def test_frontend_assets_exist() -> None:
    assert _FRONTEND.is_dir(), f"missing {_FRONTEND}"
    for name in ("index.html", "app.js", "styles.css"):
        assert (_FRONTEND / name).is_file(), f"missing {name}"


def test_health_route_registered() -> None:
    app = create_app()
    paths = []
    for route in app.routes:
        try:
            paths.append(route.path)
        except Exception:
            pass
    assert "/health" in paths
