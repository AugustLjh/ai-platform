"""Introduce async vector indexing jobs and remove PostgreSQL embedding storage."""

from __future__ import annotations

from alembic import op


revision = "20260319_0003"
down_revision = "20260319_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        ALTER TABLE public.documents
            ADD COLUMN IF NOT EXISTS embedding_model_key character varying(255),
            ADD COLUMN IF NOT EXISTS embedding_dimension integer,
            ADD COLUMN IF NOT EXISTS index_status character varying(20) DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS index_version integer DEFAULT 1,
            ADD COLUMN IF NOT EXISTS last_index_error text;

        UPDATE public.documents
        SET embedding_dimension = COALESCE(embedding_dimension, array_length(embedding, 1)),
            embedding_model_key = COALESCE(embedding_model_key, NULLIF(metadata->>'vector_embedding_model_key', '')),
            index_status = CASE
                WHEN indexed THEN 'ready'
                ELSE 'pending'
            END,
            index_version = COALESCE(index_version, 1)
        WHERE true;

        ALTER TABLE public.documents
            ALTER COLUMN index_status SET NOT NULL,
            ALTER COLUMN index_version SET NOT NULL;

        ALTER TABLE public.documents
            DROP COLUMN IF EXISTS embedding;

        ALTER TABLE public.document_chunks
            ADD COLUMN IF NOT EXISTS chunk_hash character varying(64);

        UPDATE public.document_chunks
        SET chunk_hash = md5(COALESCE(content, ''))
        WHERE chunk_hash IS NULL;

        ALTER TABLE public.document_chunks
            DROP COLUMN IF EXISTS embedding_model,
            DROP COLUMN IF EXISTS embedding;

        CREATE TABLE IF NOT EXISTS public.document_index_jobs (
            id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
            tenant_id uuid NOT NULL,
            knowledge_base_id uuid,
            document_id uuid NOT NULL,
            job_type character varying(20) NOT NULL,
            target_version integer,
            status character varying(20) DEFAULT 'pending' NOT NULL,
            attempts integer DEFAULT 0 NOT NULL,
            next_run_at timestamp with time zone DEFAULT now() NOT NULL,
            started_at timestamp with time zone,
            completed_at timestamp with time zone,
            last_error text,
            payload jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT document_index_jobs_pkey PRIMARY KEY (id),
            CONSTRAINT document_index_jobs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE,
            CONSTRAINT document_index_jobs_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
            CONSTRAINT document_index_jobs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_documents_index_status ON public.documents USING btree (index_status);
        CREATE INDEX IF NOT EXISTS idx_document_chunks_chunk_hash ON public.document_chunks USING btree (chunk_hash);
        CREATE INDEX IF NOT EXISTS idx_document_index_jobs_status_run_at ON public.document_index_jobs USING btree (status, next_run_at);
        CREATE INDEX IF NOT EXISTS idx_document_index_jobs_document_id ON public.document_index_jobs USING btree (document_id);
        CREATE INDEX IF NOT EXISTS idx_document_index_jobs_tenant_id ON public.document_index_jobs USING btree (tenant_id);

        DROP TRIGGER IF EXISTS update_document_index_jobs_updated_at ON public.document_index_jobs;
        CREATE TRIGGER update_document_index_jobs_updated_at
            BEFORE UPDATE ON public.document_index_jobs
            FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TRIGGER IF EXISTS update_document_index_jobs_updated_at ON public.document_index_jobs;
        DROP TABLE IF EXISTS public.document_index_jobs;

        ALTER TABLE public.document_chunks
            ADD COLUMN IF NOT EXISTS embedding_model character varying(100),
            ADD COLUMN IF NOT EXISTS embedding double precision[];

        ALTER TABLE public.documents
            ADD COLUMN IF NOT EXISTS embedding double precision[];

        DROP INDEX IF EXISTS idx_document_chunks_chunk_hash;
        DROP INDEX IF EXISTS idx_documents_index_status;

        ALTER TABLE public.document_chunks
            DROP COLUMN IF EXISTS chunk_hash;

        ALTER TABLE public.documents
            DROP COLUMN IF EXISTS embedding_model_key,
            DROP COLUMN IF EXISTS embedding_dimension,
            DROP COLUMN IF EXISTS index_status,
            DROP COLUMN IF EXISTS index_version,
            DROP COLUMN IF EXISTS last_index_error;
        """
    )
