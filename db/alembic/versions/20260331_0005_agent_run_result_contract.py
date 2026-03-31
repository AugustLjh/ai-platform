"""Add structured run result columns for agent runs."""

from __future__ import annotations

from alembic import op


revision = "20260331_0005"
down_revision = "20260320_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.agent_runs
            ADD COLUMN IF NOT EXISTS final_output_text text,
            ADD COLUMN IF NOT EXISTS final_output_json jsonb;

        COMMENT ON COLUMN public.agent_runs.final_output_text IS 'Primary human-readable run output used by the workspace.';
        COMMENT ON COLUMN public.agent_runs.final_output_json IS 'Structured run output shaped by skill output schema.';
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.agent_runs
            DROP COLUMN IF EXISTS final_output_json,
            DROP COLUMN IF EXISTS final_output_text;
        """
    )
