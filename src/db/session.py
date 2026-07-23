"""Database session factory — multi-backend.

Supports:
- MsSQL (via sqlalchemy + pyodbc): AGENT_DATABASE_URL = mssql+pyodbc://...
- SQLite (dev / fallback): AGENT_DATABASE_URL = sqlite:///./data/app.db

The SessionFactory is parameterised so tests can swap in a :memory: engine.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import get_settings


_ENGINE = None
_SESSION_MAKER = None


def _get_engine():
    global _ENGINE, _SESSION_MAKER
    if _ENGINE is None:
        settings = get_settings()
        url = settings.database_url
        # MsSQL needs fast_executemany=True via connect_args
        connect_args = {}
        if url.startswith("mssql"):
            connect_args["fast_executemany"] = True
        _ENGINE = create_engine(url, connect_args=connect_args, echo=False)
        _SESSION_MAKER = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False)
    return _ENGINE


def _make_session() -> Session:
    _get_engine()
    return _SESSION_MAKER()  # type: ignore[union-attr]


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and commit/rollback on exit."""
    session = _make_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_db_session() -> Session:
    """Return a raw session (caller must close / commit). Used by runner."""
    return _make_session()


def data_source_from_url(url: str) -> str:
    if "mssql" in url:
        return "mssql"
    if ":memory:" in url or "sqlite" in url:
        return "sqlite"
    return "unknown"


def init_db() -> None:
    """Create all tables if they don't exist (dev fallback)."""
    from src.db.models import Base
    Base.metadata.create_all(bind=_get_engine())
