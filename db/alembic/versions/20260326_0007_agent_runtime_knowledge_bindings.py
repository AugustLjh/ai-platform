"""Add knowledge-base bindings for agent runtime."""

from __future__ import annotations

from alembic import op


revision = "20260326_0007"
down_revision = "20260320_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.agent_knowledge_bindings (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            agent_definition_id uuid NOT NULL,
            knowledge_base_id uuid NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT agent_knowledge_bindings_pkey PRIMARY KEY (id),
            CONSTRAINT agent_knowledge_bindings_agent_definition_id_fkey FOREIGN KEY (agent_definition_id) REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT agent_knowledge_bindings_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
            CONSTRAINT agent_knowledge_bindings_agent_definition_id_knowledge_base_id_key UNIQUE (agent_definition_id, knowledge_base_id)
        );

        CREATE INDEX IF NOT EXISTS idx_agent_knowledge_bindings_agent_definition_id
            ON public.agent_knowledge_bindings USING btree (agent_definition_id);
        CREATE INDEX IF NOT EXISTS idx_agent_knowledge_bindings_knowledge_base_id
            ON public.agent_knowledge_bindings USING btree (knowledge_base_id);

        DROP TRIGGER IF EXISTS update_agent_knowledge_bindings_updated_at ON public.agent_knowledge_bindings;
        CREATE TRIGGER update_agent_knowledge_bindings_updated_at
            BEFORE UPDATE ON public.agent_knowledge_bindings
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TRIGGER IF EXISTS update_agent_knowledge_bindings_updated_at ON public.agent_knowledge_bindings;
        DROP TABLE IF EXISTS public.agent_knowledge_bindings;
        """
    )
