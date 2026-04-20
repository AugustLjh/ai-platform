"""Add agent runtime core persistence tables."""

from __future__ import annotations

from alembic import op


revision = "20260320_0004"
down_revision = "20260319_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.agent_definitions (
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
            CONSTRAINT agent_definitions_pkey PRIMARY KEY (id),
            CONSTRAINT agent_definitions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
            CONSTRAINT agent_definitions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT agent_definitions_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT agent_definitions_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'archived'::character varying])::text[])))
        );

        CREATE TABLE IF NOT EXISTS public.agent_runs (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            agent_definition_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            user_id uuid,
            session_id uuid,
            status character varying(20) DEFAULT 'queued' NOT NULL,
            input jsonb DEFAULT '{}'::jsonb NOT NULL,
            plan jsonb DEFAULT '{}'::jsonb NOT NULL,
            context jsonb DEFAULT '{}'::jsonb NOT NULL,
            final_output text,
            error_message text,
            started_at timestamp with time zone,
            finished_at timestamp with time zone,
            cancelled_at timestamp with time zone,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            CONSTRAINT agent_runs_pkey PRIMARY KEY (id),
            CONSTRAINT agent_runs_agent_definition_id_fkey FOREIGN KEY (agent_definition_id) REFERENCES public.agent_definitions(id) ON DELETE RESTRICT,
            CONSTRAINT agent_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
            CONSTRAINT agent_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT agent_runs_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id) ON DELETE SET NULL,
            CONSTRAINT agent_runs_status_check CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'running'::character varying, 'waiting_user'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[])))
        );

        CREATE TABLE IF NOT EXISTS public.agent_run_steps (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            run_id uuid NOT NULL,
            step_index integer NOT NULL,
            title character varying(255),
            kind character varying(50) NOT NULL,
            status character varying(20) DEFAULT 'pending' NOT NULL,
            input jsonb DEFAULT '{}'::jsonb NOT NULL,
            output jsonb DEFAULT '{}'::jsonb NOT NULL,
            error_message text,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            started_at timestamp with time zone,
            completed_at timestamp with time zone,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_run_steps_pkey PRIMARY KEY (id),
            CONSTRAINT agent_run_steps_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.agent_runs(id) ON DELETE CASCADE,
            CONSTRAINT agent_run_steps_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[]))),
            CONSTRAINT agent_run_steps_run_id_step_index_key UNIQUE (run_id, step_index)
        );

        CREATE TABLE IF NOT EXISTS public.agent_run_events (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            run_id uuid NOT NULL,
            sequence bigint NOT NULL,
            event_type character varying(100) NOT NULL,
            payload jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_run_events_pkey PRIMARY KEY (id),
            CONSTRAINT agent_run_events_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.agent_runs(id) ON DELETE CASCADE,
            CONSTRAINT agent_run_events_run_id_sequence_key UNIQUE (run_id, sequence)
        );

        CREATE TABLE IF NOT EXISTS public.agent_tool_calls (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            run_id uuid NOT NULL,
            step_id uuid,
            tool_name character varying(255) NOT NULL,
            tool_kind character varying(50) DEFAULT 'builtin' NOT NULL,
            status character varying(20) DEFAULT 'pending' NOT NULL,
            arguments jsonb DEFAULT '{}'::jsonb NOT NULL,
            result jsonb DEFAULT '{}'::jsonb NOT NULL,
            error_message text,
            started_at timestamp with time zone,
            completed_at timestamp with time zone,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_tool_calls_pkey PRIMARY KEY (id),
            CONSTRAINT agent_tool_calls_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.agent_runs(id) ON DELETE CASCADE,
            CONSTRAINT agent_tool_calls_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.agent_run_steps(id) ON DELETE SET NULL,
            CONSTRAINT agent_tool_calls_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'running'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
        );

        CREATE TABLE IF NOT EXISTS public.agent_artifacts (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            run_id uuid NOT NULL,
            step_id uuid,
            artifact_type character varying(50) NOT NULL,
            name character varying(255) NOT NULL,
            mime_type character varying(255),
            uri text,
            payload jsonb DEFAULT '{}'::jsonb NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_artifacts_pkey PRIMARY KEY (id),
            CONSTRAINT agent_artifacts_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.agent_runs(id) ON DELETE CASCADE,
            CONSTRAINT agent_artifacts_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.agent_run_steps(id) ON DELETE SET NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_definitions_active_name
            ON public.agent_definitions USING btree (tenant_id, lower(name))
            WHERE status = 'active';
        CREATE INDEX IF NOT EXISTS idx_agent_definitions_tenant_id ON public.agent_definitions USING btree (tenant_id);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_definition_id ON public.agent_runs USING btree (agent_definition_id);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_tenant_status_created_at ON public.agent_runs USING btree (tenant_id, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_agent_runs_user_created_at ON public.agent_runs USING btree (user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run_id_step_index ON public.agent_run_steps USING btree (run_id, step_index);
        CREATE INDEX IF NOT EXISTS idx_agent_run_events_run_id_sequence ON public.agent_run_events USING btree (run_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_run_id_created_at ON public.agent_tool_calls USING btree (run_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_artifacts_run_id_created_at ON public.agent_artifacts USING btree (run_id, created_at);

        COMMENT ON TABLE public.agent_definitions IS 'Agent definitions managed by the Go control plane.';
        COMMENT ON TABLE public.agent_runs IS 'Agent run lifecycles owned by the Python runtime.';
        COMMENT ON TABLE public.agent_run_steps IS 'Structured execution steps for an agent run.';
        COMMENT ON TABLE public.agent_run_events IS 'Ordered event log emitted during agent execution.';
        COMMENT ON TABLE public.agent_tool_calls IS 'Tool invocation tracing for agent runs.';
        COMMENT ON TABLE public.agent_artifacts IS 'Structured artifacts emitted by agent runs.';

        DROP TRIGGER IF EXISTS update_agent_definitions_updated_at ON public.agent_definitions;
        CREATE TRIGGER update_agent_definitions_updated_at
            BEFORE UPDATE ON public.agent_definitions
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_runs_updated_at ON public.agent_runs;
        CREATE TRIGGER update_agent_runs_updated_at
            BEFORE UPDATE ON public.agent_runs
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_run_steps_updated_at ON public.agent_run_steps;
        CREATE TRIGGER update_agent_run_steps_updated_at
            BEFORE UPDATE ON public.agent_run_steps
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_tool_calls_updated_at ON public.agent_tool_calls;
        CREATE TRIGGER update_agent_tool_calls_updated_at
            BEFORE UPDATE ON public.agent_tool_calls
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_artifacts_updated_at ON public.agent_artifacts;
        CREATE TRIGGER update_agent_artifacts_updated_at
            BEFORE UPDATE ON public.agent_artifacts
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TRIGGER IF EXISTS update_agent_artifacts_updated_at ON public.agent_artifacts;
        DROP TRIGGER IF EXISTS update_agent_tool_calls_updated_at ON public.agent_tool_calls;
        DROP TRIGGER IF EXISTS update_agent_run_steps_updated_at ON public.agent_run_steps;
        DROP TRIGGER IF EXISTS update_agent_runs_updated_at ON public.agent_runs;
        DROP TRIGGER IF EXISTS update_agent_definitions_updated_at ON public.agent_definitions;

        DROP TABLE IF EXISTS public.agent_artifacts;
        DROP TABLE IF EXISTS public.agent_tool_calls;
        DROP TABLE IF EXISTS public.agent_run_events;
        DROP TABLE IF EXISTS public.agent_run_steps;
        DROP TABLE IF EXISTS public.agent_runs;
        DROP TABLE IF EXISTS public.agent_definitions;
        """
    )
