"""add_uploaded_data

Revision ID: f00500e39f55
Revises: 0256a49dd020
Create Date: 2026-07-24 13:57:29.136215
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f00500e39f55'
down_revision: Union[str, None] = '0256a49dd020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'uploaded_data',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('original_filename', sa.Text, nullable=False),
        sa.Column('stored_filename', sa.Text, nullable=False, unique=True),
        sa.Column('mime_type', sa.Text, nullable=True),
        sa.Column('size_bytes', sa.BigInteger, nullable=True),
        sa.Column('row_count', sa.BigInteger, nullable=True),
        sa.Column('columns_json', sa.JSON, nullable=True),
        sa.Column('table_name', sa.Text, nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('uploaded_data')
