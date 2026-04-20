"""Add subagent publication governance history table."""

from __future__ import annotations

from alembic import op


revision = "20260415_0009"
down_revision = "20260415_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.subagent_publication_events (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            tenant_id uuid NOT NULL,
            subagent_definition_id uuid NOT NULL,
            publication_id uuid,
            event_stage character varying(32) DEFAULT 'executed' NOT NULL,
            action_type character varying(32) DEFAULT '' NOT NULL,
            change_type character varying(32) DEFAULT '' NOT NULL,
            risk_level character varying(16) DEFAULT '' NOT NULL,
            requires_confirmation boolean DEFAULT false NOT NULL,
            confirmed boolean DEFAULT false NOT NULL,
            version_id uuid,
            version_number integer DEFAULT 0 NOT NULL,
            previous_version_id uuid,
            previous_version_number integer DEFAULT 0 NOT NULL,
            publication_scope character varying(20) DEFAULT 'tenant' NOT NULL,
            previous_publication_scope character varying(20) DEFAULT 'tenant' NOT NULL,
            status character varying(20) DEFAULT 'active' NOT NULL,
            previous_status character varying(20) DEFAULT 'active' NOT NULL,
            impacted_authorization_count integer DEFAULT 0 NOT NULL,
            enabled_authorization_count integer DEFAULT 0 NOT NULL,
            inactive_authorization_count integer DEFAULT 0 NOT NULL,
            compatibility_mode boolean DEFAULT false NOT NULL,
            summary text DEFAULT '' NOT NULL,
            change_reason text DEFAULT '' NOT NULL,
            change_notes text DEFAULT '' NOT NULL,
            rollback_recovery_plan text DEFAULT '' NOT NULL,
            recommended_actions jsonb DEFAULT '[]'::jsonb NOT NULL,
            affected_agents jsonb DEFAULT '[]'::jsonb NOT NULL,
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            actor_user_id uuid,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT subagent_publication_events_pkey PRIMARY KEY (id),
            CONSTRAINT subagent_publication_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
            CONSTRAINT subagent_publication_events_subagent_definition_id_fkey FOREIGN KEY (subagent_definition_id) REFERENCES public.subagent_definitions(id) ON DELETE CASCADE,
            CONSTRAINT subagent_publication_events_publication_id_fkey FOREIGN KEY (publication_id) REFERENCES public.subagent_publications(id) ON DELETE SET NULL,
            CONSTRAINT subagent_publication_events_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.subagent_definition_versions(id) ON DELETE SET NULL,
            CONSTRAINT subagent_publication_events_previous_version_id_fkey FOREIGN KEY (previous_version_id) REFERENCES public.subagent_definition_versions(id) ON DELETE SET NULL,
            CONSTRAINT subagent_publication_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_subagent_publication_events_definition_created_at
            ON public.subagent_publication_events USING btree (subagent_definition_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_subagent_publication_events_tenant_created_at
            ON public.subagent_publication_events USING btree (tenant_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_subagent_publication_events_stage
            ON public.subagent_publication_events USING btree (tenant_id, event_stage, created_at DESC);
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TABLE IF EXISTS public.subagent_publication_events;
        """
    )
