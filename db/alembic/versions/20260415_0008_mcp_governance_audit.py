"""Add MCP governance audit event table."""

from __future__ import annotations

from alembic import op


revision = "20260415_0008"
down_revision = "20260401_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS public.mcp_server_events (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            tenant_id uuid NOT NULL,
            server_id uuid,
            server_name character varying(255) DEFAULT '' NOT NULL,
            event_type character varying(64) NOT NULL,
            action_type character varying(32) DEFAULT '' NOT NULL,
            status character varying(32) DEFAULT 'info' NOT NULL,
            failure_mode character varying(64),
            summary text DEFAULT '' NOT NULL,
            details jsonb DEFAULT '{}'::jsonb NOT NULL,
            actor_user_id uuid,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT mcp_server_events_pkey PRIMARY KEY (id),
            CONSTRAINT mcp_server_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
            CONSTRAINT mcp_server_events_server_id_fkey FOREIGN KEY (server_id) REFERENCES public.mcp_servers(id) ON DELETE SET NULL,
            CONSTRAINT mcp_server_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_mcp_server_events_tenant_created_at
            ON public.mcp_server_events USING btree (tenant_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mcp_server_events_server_created_at
            ON public.mcp_server_events USING btree (server_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_mcp_server_events_failure_mode
            ON public.mcp_server_events USING btree (tenant_id, failure_mode, created_at DESC);
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TABLE IF EXISTS public.mcp_server_events;
        """
    )
