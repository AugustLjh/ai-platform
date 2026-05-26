"""Allow cancelled tool calls and align structured tool failure recovery."""

from __future__ import annotations

from alembic import op


revision = "20260515_0013"
down_revision = "20260512_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.agent_tool_calls
            DROP CONSTRAINT IF EXISTS agent_tool_calls_status_check;

        ALTER TABLE public.agent_tool_calls
            ADD CONSTRAINT agent_tool_calls_status_check
            CHECK (
                (status)::text = ANY (
                    ARRAY[
                        'pending'::character varying,
                        'running'::character varying,
                        'completed'::character varying,
                        'failed'::character varying,
                        'cancelled'::character varying
                    ]::text[]
                )
            );
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.agent_tool_calls
            DROP CONSTRAINT IF EXISTS agent_tool_calls_status_check;

        UPDATE public.agent_tool_calls
        SET status = 'failed'
        WHERE status = 'cancelled';

        ALTER TABLE public.agent_tool_calls
            ADD CONSTRAINT agent_tool_calls_status_check
            CHECK (
                (status)::text = ANY (
                    ARRAY[
                        'pending'::character varying,
                        'running'::character varying,
                        'completed'::character varying,
                        'failed'::character varying
                    ]::text[]
                )
            );
        """
    )
