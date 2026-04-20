"""Persist skill contract governance state."""

from __future__ import annotations

from alembic import op


revision = "20260415_0010"
down_revision = "20260415_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.skills
        ADD COLUMN IF NOT EXISTS contract jsonb DEFAULT '{}'::jsonb NOT NULL;
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.skills
        DROP COLUMN IF EXISTS contract;
        """
    )
