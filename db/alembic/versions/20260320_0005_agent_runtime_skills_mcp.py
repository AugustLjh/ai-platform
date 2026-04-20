"""Add skill and MCP persistence for agent runtime."""

from __future__ import annotations

from alembic import op


revision = "20260320_0005"
down_revision = "20260320_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.skills (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            tenant_id uuid,
            name character varying(255) NOT NULL,
            slug character varying(255) NOT NULL,
            version character varying(50) DEFAULT '1' NOT NULL,
            description text,
            root_path text NOT NULL,
            system_prompt text DEFAULT '' NOT NULL,
            output_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
            tool_allowlist jsonb DEFAULT '[]'::jsonb NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            contract jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT skills_pkey PRIMARY KEY (id),
            CONSTRAINT skills_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS public.agent_skill_bindings (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            agent_definition_id uuid NOT NULL,
            skill_id uuid NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_skill_bindings_pkey PRIMARY KEY (id),
            CONSTRAINT agent_skill_bindings_agent_definition_id_fkey FOREIGN KEY (agent_definition_id) REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT agent_skill_bindings_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE,
            CONSTRAINT agent_skill_bindings_agent_definition_id_skill_id_key UNIQUE (agent_definition_id, skill_id)
        );

        CREATE TABLE IF NOT EXISTS public.mcp_servers (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            tenant_id uuid NOT NULL,
            name character varying(255) NOT NULL,
            transport character varying(20) DEFAULT 'stdio' NOT NULL,
            endpoint text,
            command text,
            args jsonb DEFAULT '[]'::jsonb NOT NULL,
            env jsonb DEFAULT '{}'::jsonb NOT NULL,
            status character varying(20) DEFAULT 'active' NOT NULL,
            last_tested_at timestamp with time zone,
            last_error text,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_by uuid,
            updated_by uuid,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT mcp_servers_pkey PRIMARY KEY (id),
            CONSTRAINT mcp_servers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
            CONSTRAINT mcp_servers_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT mcp_servers_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT mcp_servers_transport_check CHECK (((transport)::text = ANY ((ARRAY['stdio'::character varying, 'http'::character varying, 'sse'::character varying])::text[]))),
            CONSTRAINT mcp_servers_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'disabled'::character varying])::text[])))
        );

        CREATE TABLE IF NOT EXISTS public.mcp_server_tools (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            server_id uuid NOT NULL,
            tool_name character varying(255) NOT NULL,
            description text,
            input_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            discovered_at timestamp with time zone DEFAULT now() NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT mcp_server_tools_pkey PRIMARY KEY (id),
            CONSTRAINT mcp_server_tools_server_id_fkey FOREIGN KEY (server_id) REFERENCES public.mcp_servers(id) ON DELETE CASCADE,
            CONSTRAINT mcp_server_tools_server_id_tool_name_key UNIQUE (server_id, tool_name)
        );

        CREATE TABLE IF NOT EXISTS public.agent_mcp_bindings (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            agent_definition_id uuid NOT NULL,
            server_id uuid NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_mcp_bindings_pkey PRIMARY KEY (id),
            CONSTRAINT agent_mcp_bindings_agent_definition_id_fkey FOREIGN KEY (agent_definition_id) REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT agent_mcp_bindings_server_id_fkey FOREIGN KEY (server_id) REFERENCES public.mcp_servers(id) ON DELETE CASCADE,
            CONSTRAINT agent_mcp_bindings_agent_definition_id_server_id_key UNIQUE (agent_definition_id, server_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_global_slug
            ON public.skills USING btree (lower(slug))
            WHERE tenant_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_skills_tenant_slug
            ON public.skills USING btree (tenant_id, lower(slug))
            WHERE tenant_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_agent_skill_bindings_agent_definition_id ON public.agent_skill_bindings USING btree (agent_definition_id);
        CREATE INDEX IF NOT EXISTS idx_mcp_servers_tenant_id ON public.mcp_servers USING btree (tenant_id);
        CREATE INDEX IF NOT EXISTS idx_mcp_server_tools_server_id ON public.mcp_server_tools USING btree (server_id);
        CREATE INDEX IF NOT EXISTS idx_agent_mcp_bindings_agent_definition_id ON public.agent_mcp_bindings USING btree (agent_definition_id);

        COMMENT ON TABLE public.skills IS 'Skill packages that can be attached to agent definitions.';
        COMMENT ON TABLE public.mcp_servers IS 'Configured MCP servers available to a tenant.';

        DROP TRIGGER IF EXISTS update_skills_updated_at ON public.skills;
        CREATE TRIGGER update_skills_updated_at
            BEFORE UPDATE ON public.skills
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_skill_bindings_updated_at ON public.agent_skill_bindings;
        CREATE TRIGGER update_agent_skill_bindings_updated_at
            BEFORE UPDATE ON public.agent_skill_bindings
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_mcp_servers_updated_at ON public.mcp_servers;
        CREATE TRIGGER update_mcp_servers_updated_at
            BEFORE UPDATE ON public.mcp_servers
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_mcp_server_tools_updated_at ON public.mcp_server_tools;
        CREATE TRIGGER update_mcp_server_tools_updated_at
            BEFORE UPDATE ON public.mcp_server_tools
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_mcp_bindings_updated_at ON public.agent_mcp_bindings;
        CREATE TRIGGER update_agent_mcp_bindings_updated_at
            BEFORE UPDATE ON public.agent_mcp_bindings
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TRIGGER IF EXISTS update_agent_mcp_bindings_updated_at ON public.agent_mcp_bindings;
        DROP TRIGGER IF EXISTS update_mcp_server_tools_updated_at ON public.mcp_server_tools;
        DROP TRIGGER IF EXISTS update_mcp_servers_updated_at ON public.mcp_servers;
        DROP TRIGGER IF EXISTS update_agent_skill_bindings_updated_at ON public.agent_skill_bindings;
        DROP TRIGGER IF EXISTS update_skills_updated_at ON public.skills;

        DROP TABLE IF EXISTS public.agent_mcp_bindings;
        DROP TABLE IF EXISTS public.mcp_server_tools;
        DROP TABLE IF EXISTS public.mcp_servers;
        DROP TABLE IF EXISTS public.agent_skill_bindings;
        DROP TABLE IF EXISTS public.skills;
        """
    )
