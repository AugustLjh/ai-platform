"""Add subagent persistence tables."""

from __future__ import annotations

from alembic import op


revision = "20260320_0006"
down_revision = "20260320_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.subagent_definitions (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            tenant_id uuid NOT NULL,
            name character varying(255) NOT NULL,
            description text,
            system_prompt text DEFAULT '' NOT NULL,
            model character varying(255),
            status character varying(20) DEFAULT 'active' NOT NULL,
            config jsonb DEFAULT '{}'::jsonb NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_by uuid,
            updated_by uuid,
            archived_at timestamp with time zone,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT subagent_definitions_pkey PRIMARY KEY (id),
            CONSTRAINT subagent_definitions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
            CONSTRAINT subagent_definitions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT subagent_definitions_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT subagent_definitions_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'archived'::character varying])::text[])))
        );

        CREATE TABLE IF NOT EXISTS public.agent_subagent_bindings (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            agent_definition_id uuid NOT NULL,
            subagent_definition_id uuid NOT NULL,
            name_override character varying(255),
            description_override text,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_subagent_bindings_pkey PRIMARY KEY (id),
            CONSTRAINT agent_subagent_bindings_agent_definition_id_fkey FOREIGN KEY (agent_definition_id) REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT agent_subagent_bindings_subagent_definition_id_fkey FOREIGN KEY (subagent_definition_id) REFERENCES public.subagent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT agent_subagent_bindings_agent_definition_id_subagent_definition_key UNIQUE (agent_definition_id, subagent_definition_id)
        );

        CREATE TABLE IF NOT EXISTS public.agent_subagent_invocations (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            parent_run_id uuid NOT NULL,
            parent_step_id uuid,
            subagent_definition_id uuid NOT NULL,
            child_run_id uuid,
            status character varying(20) DEFAULT 'pending' NOT NULL,
            request_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
            result_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
            error_message text,
            started_at timestamp with time zone,
            completed_at timestamp with time zone,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_subagent_invocations_pkey PRIMARY KEY (id),
            CONSTRAINT agent_subagent_invocations_parent_run_id_fkey FOREIGN KEY (parent_run_id) REFERENCES public.agent_runs(id) ON DELETE CASCADE,
            CONSTRAINT agent_subagent_invocations_parent_step_id_fkey FOREIGN KEY (parent_step_id) REFERENCES public.agent_run_steps(id) ON DELETE SET NULL,
            CONSTRAINT agent_subagent_invocations_subagent_definition_id_fkey FOREIGN KEY (subagent_definition_id) REFERENCES public.subagent_definitions(id) ON DELETE RESTRICT,
            CONSTRAINT agent_subagent_invocations_child_run_id_fkey FOREIGN KEY (child_run_id) REFERENCES public.agent_runs(id) ON DELETE SET NULL,
            CONSTRAINT agent_subagent_invocations_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[])))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_subagent_definitions_active_name
            ON public.subagent_definitions USING btree (tenant_id, lower(name))
            WHERE status = 'active';
        CREATE INDEX IF NOT EXISTS idx_agent_subagent_bindings_agent_definition_id ON public.agent_subagent_bindings USING btree (agent_definition_id);
        CREATE INDEX IF NOT EXISTS idx_agent_subagent_invocations_parent_run_id ON public.agent_subagent_invocations USING btree (parent_run_id, created_at);

        COMMENT ON TABLE public.subagent_definitions IS 'Reusable specialist agents that can be delegated to.';
        COMMENT ON TABLE public.agent_subagent_invocations IS 'Nested execution records from parent agent runs.';

        DROP TRIGGER IF EXISTS update_subagent_definitions_updated_at ON public.subagent_definitions;
        CREATE TRIGGER update_subagent_definitions_updated_at
            BEFORE UPDATE ON public.subagent_definitions
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_subagent_bindings_updated_at ON public.agent_subagent_bindings;
        CREATE TRIGGER update_agent_subagent_bindings_updated_at
            BEFORE UPDATE ON public.agent_subagent_bindings
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_subagent_invocations_updated_at ON public.agent_subagent_invocations;
        CREATE TRIGGER update_agent_subagent_invocations_updated_at
            BEFORE UPDATE ON public.agent_subagent_invocations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TRIGGER IF EXISTS update_agent_subagent_invocations_updated_at ON public.agent_subagent_invocations;
        DROP TRIGGER IF EXISTS update_agent_subagent_bindings_updated_at ON public.agent_subagent_bindings;
        DROP TRIGGER IF EXISTS update_subagent_definitions_updated_at ON public.subagent_definitions;

        DROP TABLE IF EXISTS public.agent_subagent_invocations;
        DROP TABLE IF EXISTS public.agent_subagent_bindings;
        DROP TABLE IF EXISTS public.subagent_definitions;
        """
    )
