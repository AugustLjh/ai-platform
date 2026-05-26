"""Converge subagent invocation statuses with child run statuses."""

from __future__ import annotations

from alembic import op


revision = "20260512_0012"
down_revision = "20260415_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.agent_subagent_invocations
            DROP CONSTRAINT IF EXISTS agent_subagent_invocations_status_check;

        UPDATE public.agent_subagent_invocations
        SET status = 'queued'
        WHERE status = 'pending';

        ALTER TABLE public.agent_subagent_invocations
            ALTER COLUMN status SET DEFAULT 'queued';

        ALTER TABLE public.agent_subagent_invocations
            ADD CONSTRAINT agent_subagent_invocations_status_check
            CHECK (
                (status)::text = ANY (
                    ARRAY[
                        'queued'::character varying,
                        'running'::character varying,
                        'waiting_user'::character varying,
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
        ALTER TABLE public.agent_subagent_invocations
            DROP CONSTRAINT IF EXISTS agent_subagent_invocations_status_check;

        UPDATE public.agent_subagent_invocations
        SET status = 'pending'
        WHERE status = 'queued';

        ALTER TABLE public.agent_subagent_invocations
            ALTER COLUMN status SET DEFAULT 'pending';

        ALTER TABLE public.agent_subagent_invocations
            ADD CONSTRAINT agent_subagent_invocations_status_check
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
