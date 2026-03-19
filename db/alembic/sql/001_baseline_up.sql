CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TABLE public.tenants (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    plan character varying(50) DEFAULT 'free'::character varying NOT NULL,
    active boolean DEFAULT true NOT NULL,
    settings jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tenants_pkey PRIMARY KEY (id),
    CONSTRAINT tenants_slug_key UNIQUE (slug)
);

CREATE TABLE public.users (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    tenant_id uuid NOT NULL,
    role character varying(50) DEFAULT 'user'::character varying NOT NULL,
    active boolean DEFAULT true NOT NULL,
    email_verified boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_login_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_email_key UNIQUE (email),
    CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE
);

CREATE TABLE public.sessions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    title character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_message_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT sessions_pkey PRIMARY KEY (id),
    CONSTRAINT sessions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);

CREATE TABLE public.knowledge_bases (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid,
    name character varying(255) NOT NULL,
    description text,
    access_level character varying(20) DEFAULT 'tenant'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT knowledge_bases_pkey PRIMARY KEY (id),
    CONSTRAINT check_kb_access_level CHECK (((access_level)::text = ANY ((ARRAY['tenant'::character varying, 'user'::character varying])::text[]))),
    CONSTRAINT knowledge_bases_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT knowledge_bases_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE TABLE public.documents (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    content text NOT NULL,
    source character varying(255),
    source_type character varying(50),
    embedding_model character varying(100),
    embedding_model_key character varying(255),
    embedding_dimension integer,
    indexed boolean DEFAULT false NOT NULL,
    indexed_at timestamp with time zone,
    index_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    index_version integer DEFAULT 1 NOT NULL,
    last_index_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    user_id uuid,
    access_level character varying(20) DEFAULT 'tenant'::character varying NOT NULL,
    knowledge_base_id uuid NOT NULL,
    search_terms text DEFAULT ''::text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (((setweight(to_tsvector('simple'::regconfig, (COALESCE(title, ''::character varying))::text), 'A'::"char") || setweight(to_tsvector('simple'::regconfig, COALESCE(content, ''::text)), 'B'::"char")) || setweight(to_tsvector('simple'::regconfig, COALESCE(search_terms, ''::text)), 'A'::"char"))) STORED,
    CONSTRAINT documents_pkey PRIMARY KEY (id),
    CONSTRAINT check_access_level CHECK (((access_level)::text = ANY ((ARRAY['tenant'::character varying, 'user'::character varying])::text[]))),
    CONSTRAINT check_source_type CHECK (((source_type)::text = ANY ((ARRAY['file'::character varying, 'url'::character varying, 'manual'::character varying, 'batch'::character varying])::text[]))),
    CONSTRAINT documents_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
    CONSTRAINT documents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT documents_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE TABLE public.document_chunks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    document_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    knowledge_base_id uuid NOT NULL,
    user_id uuid,
    access_level character varying(20) DEFAULT 'tenant'::character varying NOT NULL,
    chunk_index integer NOT NULL,
    start_offset integer DEFAULT 0 NOT NULL,
    end_offset integer DEFAULT 0 NOT NULL,
    char_count integer DEFAULT 0 NOT NULL,
    title character varying(255) NOT NULL,
    content text NOT NULL,
    source character varying(255),
    source_type character varying(50),
    chunk_hash character varying(64),
    search_terms text DEFAULT ''::text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (((setweight(to_tsvector('simple'::regconfig, (COALESCE(title, ''::character varying))::text), 'A'::"char") || setweight(to_tsvector('simple'::regconfig, COALESCE(content, ''::text)), 'B'::"char")) || setweight(to_tsvector('simple'::regconfig, COALESCE(search_terms, ''::text)), 'A'::"char"))) STORED,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT document_chunks_pkey PRIMARY KEY (id),
    CONSTRAINT uq_document_chunks_document_chunk UNIQUE (document_id, chunk_index),
    CONSTRAINT document_chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE,
    CONSTRAINT document_chunks_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
    CONSTRAINT document_chunks_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT document_chunks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE TABLE public.document_index_jobs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    knowledge_base_id uuid,
    document_id uuid NOT NULL,
    job_type character varying(20) NOT NULL,
    target_version integer,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
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

CREATE TABLE public.llm_models (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(100) NOT NULL,
    display_name character varying(255) NOT NULL,
    provider character varying(50) NOT NULL,
    model_id character varying(100) NOT NULL,
    api_base character varying(500),
    api_key_encrypted text,
    config jsonb DEFAULT '{}'::jsonb,
    enabled boolean DEFAULT true NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by uuid,
    tenant_id uuid,
    metadata jsonb DEFAULT '{}'::jsonb,
    model_type character varying(20) DEFAULT 'llm'::character varying NOT NULL,
    CONSTRAINT llm_models_pkey PRIMARY KEY (id),
    CONSTRAINT llm_models_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL,
    CONSTRAINT llm_models_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE
);

CREATE TABLE public.messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    session_id uuid NOT NULL,
    role character varying(50) NOT NULL,
    content text NOT NULL,
    token_count integer DEFAULT 0,
    model character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    model_id uuid,
    CONSTRAINT messages_pkey PRIMARY KEY (id),
    CONSTRAINT messages_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.llm_models(id) ON DELETE SET NULL,
    CONSTRAINT messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id) ON DELETE CASCADE
);

CREATE TABLE public.token_usage (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    session_id uuid,
    message_id uuid,
    model character varying(100) NOT NULL,
    prompt_tokens integer DEFAULT 0 NOT NULL,
    completion_tokens integer DEFAULT 0 NOT NULL,
    total_tokens integer DEFAULT 0 NOT NULL,
    cost numeric(10,6) DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT token_usage_pkey PRIMARY KEY (id),
    CONSTRAINT token_usage_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE,
    CONSTRAINT token_usage_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id) ON DELETE CASCADE,
    CONSTRAINT token_usage_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT token_usage_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);

CREATE TABLE public.api_keys (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    key_hash character varying(255) NOT NULL,
    key_prefix character varying(20) NOT NULL,
    scopes text[] DEFAULT ARRAY[]::text[],
    active boolean DEFAULT true NOT NULL,
    expires_at timestamp with time zone,
    last_used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT api_keys_pkey PRIMARY KEY (id),
    CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash),
    CONSTRAINT api_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);

CREATE TABLE public.audit_logs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid,
    tenant_id uuid,
    action character varying(100) NOT NULL,
    resource_type character varying(100) NOT NULL,
    resource_id uuid,
    ip_address inet,
    user_agent text,
    details jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_logs_pkey PRIMARY KEY (id),
    CONSTRAINT audit_logs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE SET NULL,
    CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE TABLE public.quotas (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    quota_type character varying(50) NOT NULL,
    limit_value bigint NOT NULL,
    current_value bigint DEFAULT 0 NOT NULL,
    reset_period character varying(20) NOT NULL,
    last_reset_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    period_start timestamp with time zone DEFAULT now(),
    period_end timestamp with time zone DEFAULT (now() + '1 mon'::interval),
    CONSTRAINT quotas_pkey PRIMARY KEY (id),
    CONSTRAINT quotas_tenant_id_quota_type_key UNIQUE (tenant_id, quota_type),
    CONSTRAINT quotas_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE
);

CREATE TABLE public.retrieval_test_sets (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    knowledge_base_id uuid NOT NULL,
    user_id uuid,
    name character varying(255) NOT NULL,
    description text,
    cases jsonb DEFAULT '[]'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT retrieval_test_sets_pkey PRIMARY KEY (id),
    CONSTRAINT retrieval_test_sets_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
    CONSTRAINT retrieval_test_sets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT retrieval_test_sets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE TABLE public.retrieval_test_runs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    knowledge_base_id uuid NOT NULL,
    test_set_id uuid,
    user_id uuid,
    name character varying(255),
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    results jsonb DEFAULT '[]'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT retrieval_test_runs_pkey PRIMARY KEY (id),
    CONSTRAINT retrieval_test_runs_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE,
    CONSTRAINT retrieval_test_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE,
    CONSTRAINT retrieval_test_runs_test_set_id_fkey FOREIGN KEY (test_set_id) REFERENCES public.retrieval_test_sets(id) ON DELETE SET NULL,
    CONSTRAINT retrieval_test_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL
);

CREATE INDEX idx_users_email ON public.users USING btree (email);
CREATE INDEX idx_users_tenant_id ON public.users USING btree (tenant_id);
CREATE INDEX idx_users_active ON public.users USING btree (active);
CREATE INDEX idx_users_created_at ON public.users USING btree (created_at);

CREATE INDEX idx_sessions_user_id ON public.sessions USING btree (user_id);
CREATE INDEX idx_sessions_tenant_id ON public.sessions USING btree (tenant_id);
CREATE INDEX idx_sessions_created_at ON public.sessions USING btree (created_at DESC);
CREATE INDEX idx_sessions_last_message_at ON public.sessions USING btree (last_message_at DESC);

CREATE INDEX idx_messages_session_id ON public.messages USING btree (session_id);
CREATE INDEX idx_messages_created_at ON public.messages USING btree (created_at);
CREATE INDEX idx_messages_role ON public.messages USING btree (role);
CREATE INDEX idx_messages_model_id ON public.messages USING btree (model_id);

CREATE INDEX idx_token_usage_user_id ON public.token_usage USING btree (user_id);
CREATE INDEX idx_token_usage_tenant_id ON public.token_usage USING btree (tenant_id);
CREATE INDEX idx_token_usage_session_id ON public.token_usage USING btree (session_id);
CREATE INDEX idx_token_usage_created_at ON public.token_usage USING btree (created_at DESC);

CREATE INDEX idx_api_keys_user_id ON public.api_keys USING btree (user_id);
CREATE INDEX idx_api_keys_tenant_id ON public.api_keys USING btree (tenant_id);
CREATE INDEX idx_api_keys_key_hash ON public.api_keys USING btree (key_hash);
CREATE INDEX idx_api_keys_active ON public.api_keys USING btree (active);

CREATE INDEX idx_documents_tenant_id ON public.documents USING btree (tenant_id);
CREATE INDEX idx_documents_indexed ON public.documents USING btree (indexed);
CREATE INDEX idx_documents_created_at ON public.documents USING btree (created_at DESC);
CREATE INDEX idx_documents_user_id ON public.documents USING btree (user_id);
CREATE INDEX idx_documents_access_level ON public.documents USING btree (access_level);
CREATE INDEX idx_documents_source_type ON public.documents USING btree (source_type);
CREATE INDEX idx_documents_knowledge_base_id ON public.documents USING btree (knowledge_base_id);
CREATE INDEX idx_documents_index_status ON public.documents USING btree (index_status);
CREATE INDEX idx_documents_search_vector_gin ON public.documents USING gin (search_vector);

CREATE INDEX idx_audit_logs_user_id ON public.audit_logs USING btree (user_id);
CREATE INDEX idx_audit_logs_tenant_id ON public.audit_logs USING btree (tenant_id);
CREATE INDEX idx_audit_logs_action ON public.audit_logs USING btree (action);
CREATE INDEX idx_audit_logs_created_at ON public.audit_logs USING btree (created_at DESC);

CREATE INDEX idx_quotas_tenant_id ON public.quotas USING btree (tenant_id);
CREATE INDEX idx_quotas_quota_type ON public.quotas USING btree (quota_type);
CREATE INDEX idx_quotas_period_end ON public.quotas USING btree (period_end);

CREATE INDEX idx_knowledge_bases_tenant_id ON public.knowledge_bases USING btree (tenant_id);
CREATE INDEX idx_knowledge_bases_user_id ON public.knowledge_bases USING btree (user_id);
CREATE INDEX idx_knowledge_bases_access_level ON public.knowledge_bases USING btree (access_level);
CREATE INDEX idx_knowledge_bases_created_at ON public.knowledge_bases USING btree (created_at DESC);
CREATE INDEX idx_knowledge_bases_name ON public.knowledge_bases USING btree (name);

CREATE INDEX idx_llm_models_provider ON public.llm_models USING btree (provider);
CREATE INDEX idx_llm_models_enabled ON public.llm_models USING btree (enabled);
CREATE INDEX idx_llm_models_tenant_id ON public.llm_models USING btree (tenant_id);
CREATE INDEX idx_llm_models_is_default ON public.llm_models USING btree (is_default);
CREATE INDEX idx_llm_models_model_type ON public.llm_models USING btree (model_type);
CREATE UNIQUE INDEX idx_llm_models_default_per_tenant ON public.llm_models USING btree (tenant_id, is_default) WHERE (is_default = true);

CREATE INDEX idx_retrieval_test_sets_tenant_id ON public.retrieval_test_sets USING btree (tenant_id);
CREATE INDEX idx_retrieval_test_sets_kb_id ON public.retrieval_test_sets USING btree (knowledge_base_id);
CREATE INDEX idx_retrieval_test_sets_created_at ON public.retrieval_test_sets USING btree (created_at DESC);

CREATE INDEX idx_retrieval_test_runs_tenant_id ON public.retrieval_test_runs USING btree (tenant_id);
CREATE INDEX idx_retrieval_test_runs_kb_id ON public.retrieval_test_runs USING btree (knowledge_base_id);
CREATE INDEX idx_retrieval_test_runs_test_set_id ON public.retrieval_test_runs USING btree (test_set_id);
CREATE INDEX idx_retrieval_test_runs_created_at ON public.retrieval_test_runs USING btree (created_at DESC);

CREATE INDEX idx_document_chunks_document_id ON public.document_chunks USING btree (document_id);
CREATE INDEX idx_document_chunks_tenant_id ON public.document_chunks USING btree (tenant_id);
CREATE INDEX idx_document_chunks_knowledge_base_id ON public.document_chunks USING btree (knowledge_base_id);
CREATE INDEX idx_document_chunks_access_level ON public.document_chunks USING btree (access_level);
CREATE INDEX idx_document_chunks_source_type ON public.document_chunks USING btree (source_type);
CREATE INDEX idx_document_chunks_chunk_index ON public.document_chunks USING btree (document_id, chunk_index);
CREATE INDEX idx_document_chunks_chunk_hash ON public.document_chunks USING btree (chunk_hash);
CREATE INDEX idx_document_chunks_search_vector_gin ON public.document_chunks USING gin (search_vector);

CREATE INDEX idx_document_index_jobs_status_run_at ON public.document_index_jobs USING btree (status, next_run_at);
CREATE INDEX idx_document_index_jobs_document_id ON public.document_index_jobs USING btree (document_id);
CREATE INDEX idx_document_index_jobs_tenant_id ON public.document_index_jobs USING btree (tenant_id);

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON public.tenants FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_sessions_updated_at BEFORE UPDATE ON public.sessions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_documents_updated_at BEFORE UPDATE ON public.documents FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_api_keys_updated_at BEFORE UPDATE ON public.api_keys FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_quotas_updated_at BEFORE UPDATE ON public.quotas FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_knowledge_bases_updated_at BEFORE UPDATE ON public.knowledge_bases FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_document_index_jobs_updated_at BEFORE UPDATE ON public.document_index_jobs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_retrieval_test_sets_updated_at BEFORE UPDATE ON public.retrieval_test_sets FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
CREATE TRIGGER update_retrieval_test_runs_updated_at BEFORE UPDATE ON public.retrieval_test_runs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
