-- Setup permissions for ai_platform user
-- This file runs before other migrations due to 000_ prefix

-- Grant all privileges on database
GRANT ALL PRIVILEGES ON DATABASE ai_platform TO ai_platform;

-- Grant usage on public schema
GRANT USAGE ON SCHEMA public TO ai_platform;

-- Grant create on public schema
GRANT CREATE ON SCHEMA public TO ai_platform;

-- Grant all privileges on all tables in public schema
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ai_platform;

-- Grant all privileges on all sequences in public schema
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ai_platform;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ai_platform;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ai_platform;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO ai_platform;

-- Make ai_platform the owner of the public schema (optional but recommended)
-- ALTER SCHEMA public OWNER TO ai_platform;