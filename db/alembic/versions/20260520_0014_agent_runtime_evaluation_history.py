"""Persist runtime governance evaluation history."""

from __future__ import annotations

from alembic import op


revision = "20260520_0014"
down_revision = "20260515_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.agent_evaluations (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            tenant_id uuid NOT NULL,
            evaluation_type character varying(64) NOT NULL,
            suite_name character varying(255) NOT NULL,
            status character varying(32) DEFAULT 'unknown'::character varying NOT NULL,
            actor_user_id uuid,
            summary jsonb DEFAULT '{}'::jsonb NOT NULL,
            payload jsonb DEFAULT '{}'::jsonb NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_evaluations_pkey PRIMARY KEY (id),
            CONSTRAINT agent_evaluations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
            CONSTRAINT agent_evaluations_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_agent_evaluations_tenant_type_created
            ON public.agent_evaluations USING btree (tenant_id, evaluation_type, created_at DESC);

        DROP TRIGGER IF EXISTS update_agent_evaluations_updated_at ON public.agent_evaluations;
        CREATE TRIGGER update_agent_evaluations_updated_at
            BEFORE UPDATE ON public.agent_evaluations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TRIGGER IF EXISTS update_agent_evaluations_updated_at ON public.agent_evaluations;
        DROP INDEX IF EXISTS idx_agent_evaluations_tenant_type_created;
        DROP TABLE IF EXISTS public.agent_evaluations;
        """
    )
