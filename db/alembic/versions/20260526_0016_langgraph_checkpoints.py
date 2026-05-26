"""Add LangGraph checkpoint tables for AsyncPostgresSaver.

These tables are used internally by LangGraph for durable graph state
(resume, interrupt, replay). They do NOT replace the existing agent_runs /
agent_run_steps / agent_run_events tables which remain the user-visible
queryable state.
"""

from __future__ import annotations

from alembic import op


revision = "20260526_0016"
down_revision = "20260522_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            parent_checkpoint_id TEXT,
            type TEXT,
            checkpoint JSONB NOT NULL,
            metadata_ JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        );

        CREATE TABLE IF NOT EXISTS checkpoint_blobs (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            channel TEXT NOT NULL,
            version TEXT NOT NULL,
            type TEXT NOT NULL,
            blob BYTEA,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        );

        CREATE TABLE IF NOT EXISTS checkpoint_writes (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            channel TEXT NOT NULL,
            type TEXT,
            blob BYTEA NOT NULL,
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        );

        CREATE TABLE IF NOT EXISTS checkpoint_migrations (
            v INTEGER NOT NULL PRIMARY KEY
        );
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TABLE IF EXISTS checkpoint_migrations;
        DROP TABLE IF EXISTS checkpoint_writes;
        DROP TABLE IF EXISTS checkpoint_blobs;
        DROP TABLE IF EXISTS checkpoints;
        """
    )
