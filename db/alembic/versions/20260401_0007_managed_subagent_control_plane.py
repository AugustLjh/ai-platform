"""Add managed subagent versioning, publication, and authorization tables."""

from __future__ import annotations

from alembic import op


revision = "20260401_0007"
down_revision = "20260331_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.subagent_definition_versions (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            subagent_definition_id uuid NOT NULL,
            version_number integer NOT NULL,
            lifecycle_status character varying(20) DEFAULT 'draft' NOT NULL,
            system_prompt text DEFAULT '' NOT NULL,
            model character varying(255),
            config jsonb DEFAULT '{}'::jsonb NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            output_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
            handoff_input_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
            tool_allowlist jsonb DEFAULT '[]'::jsonb NOT NULL,
            skill_allowlist jsonb DEFAULT '[]'::jsonb NOT NULL,
            mcp_allowlist jsonb DEFAULT '[]'::jsonb NOT NULL,
            knowledge_policy jsonb DEFAULT '{}'::jsonb NOT NULL,
            review_policy jsonb DEFAULT '{}'::jsonb NOT NULL,
            runtime_policy jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_by uuid,
            updated_by uuid,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT subagent_definition_versions_pkey PRIMARY KEY (id),
            CONSTRAINT subagent_definition_versions_definition_id_fkey FOREIGN KEY (subagent_definition_id) REFERENCES public.subagent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT subagent_definition_versions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT subagent_definition_versions_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT subagent_definition_versions_lifecycle_status_check CHECK (((lifecycle_status)::text = ANY ((ARRAY['draft'::character varying, 'tested'::character varying, 'active'::character varying, 'deprecated'::character varying, 'archived'::character varying])::text[]))),
            CONSTRAINT subagent_definition_versions_definition_version_key UNIQUE (subagent_definition_id, version_number)
        );

        CREATE TABLE IF NOT EXISTS public.subagent_publications (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            subagent_definition_id uuid NOT NULL,
            version_id uuid NOT NULL,
            tenant_id uuid,
            visibility character varying(20) DEFAULT 'tenant' NOT NULL,
            status character varying(20) DEFAULT 'active' NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_by uuid,
            updated_by uuid,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            archived_at timestamp with time zone,
            CONSTRAINT subagent_publications_pkey PRIMARY KEY (id),
            CONSTRAINT subagent_publications_definition_id_fkey FOREIGN KEY (subagent_definition_id) REFERENCES public.subagent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT subagent_publications_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.subagent_definition_versions(id) ON DELETE CASCADE,
            CONSTRAINT subagent_publications_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
            CONSTRAINT subagent_publications_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT subagent_publications_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT subagent_publications_visibility_check CHECK (((visibility)::text = ANY ((ARRAY['tenant'::character varying, 'system_global'::character varying])::text[]))),
            CONSTRAINT subagent_publications_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'deprecated'::character varying, 'archived'::character varying])::text[])))
        );

        CREATE TABLE IF NOT EXISTS public.agent_subagent_authorizations (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            agent_definition_id uuid NOT NULL,
            publication_id uuid NOT NULL,
            status character varying(20) DEFAULT 'enabled' NOT NULL,
            priority integer DEFAULT 100 NOT NULL,
            budget_policy jsonb DEFAULT '{}'::jsonb NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_by uuid,
            updated_by uuid,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_subagent_authorizations_pkey PRIMARY KEY (id),
            CONSTRAINT agent_subagent_authorizations_agent_definition_id_fkey FOREIGN KEY (agent_definition_id) REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT agent_subagent_authorizations_publication_id_fkey FOREIGN KEY (publication_id) REFERENCES public.subagent_publications(id) ON DELETE CASCADE,
            CONSTRAINT agent_subagent_authorizations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT agent_subagent_authorizations_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL,
            CONSTRAINT agent_subagent_authorizations_status_check CHECK (((status)::text = ANY ((ARRAY['enabled'::character varying, 'disabled'::character varying])::text[]))),
            CONSTRAINT agent_subagent_authorizations_agent_publication_key UNIQUE (agent_definition_id, publication_id)
        );

        CREATE INDEX IF NOT EXISTS idx_subagent_definition_versions_definition_id
            ON public.subagent_definition_versions USING btree (subagent_definition_id, version_number DESC);
        CREATE INDEX IF NOT EXISTS idx_subagent_publications_visibility
            ON public.subagent_publications USING btree (visibility, tenant_id, status);
        CREATE INDEX IF NOT EXISTS idx_agent_subagent_authorizations_agent_definition_id
            ON public.agent_subagent_authorizations USING btree (agent_definition_id, created_at);

        ALTER TABLE public.agent_subagent_invocations
            ADD COLUMN IF NOT EXISTS publication_id uuid,
            ADD COLUMN IF NOT EXISTS version_id uuid,
            ADD COLUMN IF NOT EXISTS authorization_id uuid;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'agent_subagent_invocations_publication_id_fkey'
            ) THEN
                ALTER TABLE public.agent_subagent_invocations
                    ADD CONSTRAINT agent_subagent_invocations_publication_id_fkey
                    FOREIGN KEY (publication_id) REFERENCES public.subagent_publications(id) ON DELETE SET NULL;
            END IF;
        END$$;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'agent_subagent_invocations_version_id_fkey'
            ) THEN
                ALTER TABLE public.agent_subagent_invocations
                    ADD CONSTRAINT agent_subagent_invocations_version_id_fkey
                    FOREIGN KEY (version_id) REFERENCES public.subagent_definition_versions(id) ON DELETE SET NULL;
            END IF;
        END$$;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'agent_subagent_invocations_authorization_id_fkey'
            ) THEN
                ALTER TABLE public.agent_subagent_invocations
                    ADD CONSTRAINT agent_subagent_invocations_authorization_id_fkey
                    FOREIGN KEY (authorization_id) REFERENCES public.agent_subagent_authorizations(id) ON DELETE SET NULL;
            END IF;
        END$$;

        DROP TRIGGER IF EXISTS update_subagent_definition_versions_updated_at ON public.subagent_definition_versions;
        CREATE TRIGGER update_subagent_definition_versions_updated_at
            BEFORE UPDATE ON public.subagent_definition_versions
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_subagent_publications_updated_at ON public.subagent_publications;
        CREATE TRIGGER update_subagent_publications_updated_at
            BEFORE UPDATE ON public.subagent_publications
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

        DROP TRIGGER IF EXISTS update_agent_subagent_authorizations_updated_at ON public.agent_subagent_authorizations;
        CREATE TRIGGER update_agent_subagent_authorizations_updated_at
            BEFORE UPDATE ON public.agent_subagent_authorizations
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TRIGGER IF EXISTS update_agent_subagent_authorizations_updated_at ON public.agent_subagent_authorizations;
        DROP TRIGGER IF EXISTS update_subagent_publications_updated_at ON public.subagent_publications;
        DROP TRIGGER IF EXISTS update_subagent_definition_versions_updated_at ON public.subagent_definition_versions;

        ALTER TABLE public.agent_subagent_invocations
            DROP CONSTRAINT IF EXISTS agent_subagent_invocations_authorization_id_fkey,
            DROP CONSTRAINT IF EXISTS agent_subagent_invocations_version_id_fkey,
            DROP CONSTRAINT IF EXISTS agent_subagent_invocations_publication_id_fkey,
            DROP COLUMN IF EXISTS authorization_id,
            DROP COLUMN IF EXISTS version_id,
            DROP COLUMN IF EXISTS publication_id;

        DROP TABLE IF EXISTS public.agent_subagent_authorizations;
        DROP TABLE IF EXISTS public.subagent_publications;
        DROP TABLE IF EXISTS public.subagent_definition_versions;
        """
    )
