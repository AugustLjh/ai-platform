"""Remove pgvector objects now that Qdrant is the only vector backend."""

from __future__ import annotations

from alembic import op


revision = "20260319_0002"
down_revision = "20260318_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP INDEX IF EXISTS public.idx_documents_embedding_vector_ivfflat;
        ALTER TABLE public.documents DROP COLUMN IF EXISTS embedding_vector;
        DROP EXTENSION IF EXISTS vector;
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
        ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS embedding_vector public.vector(384);
        CREATE INDEX IF NOT EXISTS idx_documents_embedding_vector_ivfflat
            ON public.documents
            USING ivfflat (embedding_vector public.vector_cosine_ops)
            WITH (lists = '100');
        """
    )
