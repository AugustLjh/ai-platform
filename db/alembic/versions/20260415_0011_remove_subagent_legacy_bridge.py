"""Remove legacy subagent bridge after migrating bindings and metadata aliases."""

from __future__ import annotations

from alembic import op


revision = "20260415_0011"
down_revision = "20260415_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'agent_subagent_bindings'
            ) THEN
                INSERT INTO public.agent_subagent_authorizations (
                    agent_definition_id,
                    publication_id,
                    status,
                    priority,
                    budget_policy,
                    metadata,
                    created_by,
                    updated_by,
                    created_at,
                    updated_at
                )
                SELECT
                    b.agent_definition_id,
                    p.id AS publication_id,
                    'enabled'::character varying(20) AS status,
                    100 AS priority,
                    '{}'::jsonb AS budget_policy,
                    jsonb_build_object('migration_source', 'legacy_binding_removed') AS metadata,
                    NULL::uuid AS created_by,
                    NULL::uuid AS updated_by,
                    now(),
                    now()
                FROM public.agent_subagent_bindings b
                INNER JOIN public.subagent_publications p
                    ON p.subagent_definition_id = b.subagent_definition_id
                   AND p.status = 'active'
                INNER JOIN public.subagent_definitions d
                    ON d.id = b.subagent_definition_id
                INNER JOIN public.agent_definitions a
                    ON a.id = b.agent_definition_id
                WHERE d.status <> 'archived'
                  AND a.status = 'active'
                ON CONFLICT (agent_definition_id, publication_id)
                DO UPDATE SET
                    status = 'enabled',
                    metadata = public.agent_subagent_authorizations.metadata || EXCLUDED.metadata,
                    updated_at = now();

                UPDATE public.subagent_definitions
                SET
                    metadata = (
                        CASE
                            WHEN COALESCE(metadata, '{}'::jsonb) ? 'host_agent_definition_id'
                                THEN (COALESCE(metadata, '{}'::jsonb) - 'target_agent_definition_id' - 'agent_definition_id')
                            WHEN COALESCE(metadata, '{}'::jsonb) ? 'target_agent_definition_id'
                                THEN jsonb_set(
                                    (COALESCE(metadata, '{}'::jsonb) - 'target_agent_definition_id' - 'agent_definition_id'),
                                    '{host_agent_definition_id}',
                                    to_jsonb(COALESCE(metadata, '{}'::jsonb)->>'target_agent_definition_id'),
                                    true
                                )
                            WHEN COALESCE(metadata, '{}'::jsonb) ? 'agent_definition_id'
                                THEN jsonb_set(
                                    (COALESCE(metadata, '{}'::jsonb) - 'target_agent_definition_id' - 'agent_definition_id'),
                                    '{host_agent_definition_id}',
                                    to_jsonb(COALESCE(metadata, '{}'::jsonb)->>'agent_definition_id'),
                                    true
                                )
                            ELSE COALESCE(metadata, '{}'::jsonb)
                        END
                    ),
                    updated_at = now()
                WHERE COALESCE(metadata, '{}'::jsonb) ? 'target_agent_definition_id'
                   OR COALESCE(metadata, '{}'::jsonb) ? 'agent_definition_id';
            END IF;
        END$$;

        DROP TRIGGER IF EXISTS update_agent_subagent_bindings_updated_at ON public.agent_subagent_bindings;
        DROP INDEX IF EXISTS idx_agent_subagent_bindings_agent_definition_id;
        DROP TABLE IF EXISTS public.agent_subagent_bindings;
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
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

        CREATE INDEX IF NOT EXISTS idx_agent_subagent_bindings_agent_definition_id
            ON public.agent_subagent_bindings USING btree (agent_definition_id);

        DROP TRIGGER IF EXISTS update_agent_subagent_bindings_updated_at ON public.agent_subagent_bindings;
        CREATE TRIGGER update_agent_subagent_bindings_updated_at
            BEFORE UPDATE ON public.agent_subagent_bindings
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        """
    )
