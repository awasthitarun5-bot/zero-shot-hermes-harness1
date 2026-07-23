"""tests/conftest.py — test configuration and shared fixtures."""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset cached settings + engine so env patches take effect per test."""
    import src.config.settings as settings_mod
    import src.db.session as session_mod

    settings_mod._settings = None
    for attr in ("_engine", "_ENGINE", "_SessionLocal", "_SESSION_MAKER"):
        if hasattr(session_mod, attr):
            try:
                val = getattr(session_mod, attr)
                if hasattr(val, "dispose"):
                    val.dispose()
            except Exception:
                pass
            setattr(session_mod, attr, None)
    yield
    settings_mod._settings = None
    for attr in ("_engine", "_ENGINE", "_SessionLocal", "_SESSION_MAKER"):
        if hasattr(session_mod, attr):
            try:
                val = getattr(session_mod, attr)
                if hasattr(val, "dispose"):
                    val.dispose()
            except Exception:
                pass
            setattr(session_mod, attr, None)


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the app at a fresh SQLite file."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{db_path}")
    yield db_path


# Backward-compat alias used by existing tests
@pytest.fixture()
def isolated_db(temp_db):
    return temp_db


@pytest.fixture()
def no_keys(monkeypatch):
    """Blank all LLM keys."""
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "auto")
    monkeypatch.setenv("AGENT_LLM_MODEL", "")
    monkeypatch.setenv("AGENT_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "")
    monkeypatch.setenv("AGENT_OPENROUTER_API_KEY", "")
    monkeypatch.setenv("AGENT_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # Force reload of settings singleton
    import src.config.settings as settings_mod
    settings_mod._settings = None
