"""Add structured content parts to chat messages."""

from __future__ import annotations

from alembic import op


revision = "20260522_0015"
down_revision = "20260520_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.messages
        ADD COLUMN IF NOT EXISTS content_parts jsonb DEFAULT '[]'::jsonb NOT NULL;
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.messages
        DROP COLUMN IF EXISTS content_parts;
        """
    )
