"""SQLAlchemy 2.0 declarative models.

Extends the baseline RunRow with DataSource and AuditLog for the analyst agent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    TIMESTAMP,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class DataSource(str, Enum):
    """What back-end is serving the data for a given session."""
    mssql = "mssql"
    sqlite = "sqlite"
    sqlite_fallback = "sqlite_fallback"


class RunRow(Base):
    """One agent run (legacy baseline — retained for compat)."""
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    input_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class AuditLog(Base):
 """Per-query audit entry — compliance minimum."""
 __tablename__ = "audit_log"
 __table_args__ = (UniqueConstraint("session_id", name="uq_audit_session"),)

 id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
 timestamp: Mapped[datetime] = mapped_column(
 TIMESTAMP(timezone=True), nullable=False, default=_now
 )
 session_id: Mapped[str] = mapped_column(Text, nullable=False, default=_uuid)
 officer_id: Mapped[str | None] = mapped_column(Text, nullable=True)
 question: Mapped[str] = mapped_column(Text, nullable=False)
 sql: Mapped[str | None] = mapped_column(Text, nullable=True)
 row_count: Mapped[int | None] = mapped_column( nullable=True)
 duration_ms: Mapped[int | None] = mapped_column( nullable=True)
 error: Mapped[str | None] = mapped_column(Text, nullable=True)
 llm_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
 llm_model: Mapped[str | None] = mapped_column(Text, nullable=True)
 token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
 data_source: Mapped[str | None] = mapped_column(Text, nullable=True)


class UploadedData(Base):
 """Metadata for officer-uploaded CSVs."""
 __tablename__ = "uploaded_data"

 id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
 original_filename: Mapped[str] = mapped_column(Text, nullable=False)
 stored_filename: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
 mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
 size_bytes: Mapped[int | None] = mapped_column(nullable=True)
 row_count: Mapped[int | None] = mapped_column(nullable=True)
 columns_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
 table_name: Mapped[str | None] = mapped_column(Text, nullable=True)
 uploaded_at: Mapped[datetime] = mapped_column(
 TIMESTAMP(timezone=True), nullable=False, default=_now
 )
