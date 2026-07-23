"""add_audit_log

Revision ID: 0256a49dd020
Revises: 
Create Date: 2026-07-22 11:54:38.203080
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0256a49dd020"
down_revision: Union[str, None] = None
branch_labels: Union[sa.Sequence[str], sa.Sequence[sa.Sequence[str]], None] = None
depends_on: Union[sa.Sequence[str], sa.Sequence[sa.Sequence[str]], str, None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("session_id", sa.Text, nullable=False, default="unknown"),
        sa.Column("officer_id", sa.Text, nullable=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("sql", sa.Text, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("llm_provider", sa.Text, nullable=True),
        sa.Column("llm_model", sa.Text, nullable=True),
        sa.Column("token_usage", sa.JSON, nullable=True),
        sa.Column("data_source", sa.Text, nullable=True),
        sa.UniqueConstraint("session_id", name="uq_audit_session"),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_log")
