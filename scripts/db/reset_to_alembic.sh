#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_DIR="${1:-${ROOT_DIR}/tmp/db-reset-$(date +%Y%m%d%H%M%S)}"

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ai-platform-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ai_platform}"
POSTGRES_USER="${POSTGRES_USER:-ai_platform}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-19980912}"

mkdir -p "${BACKUP_DIR}"

SCHEMA_BACKUP="${BACKUP_DIR}/pre_alembic_schema.sql"
DATA_BACKUP="${BACKUP_DIR}/pre_alembic_data.dump"

export PGPASSWORD="${POSTGRES_PASSWORD}"

echo "Backing up current schema to ${SCHEMA_BACKUP}"
docker exec "${POSTGRES_CONTAINER}" pg_dump \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --schema-only \
  --no-owner \
  --no-privileges > "${SCHEMA_BACKUP}"

echo "Backing up current data to ${DATA_BACKUP}"
docker exec "${POSTGRES_CONTAINER}" pg_dump \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --format=custom \
  --data-only \
  --no-owner \
  --no-privileges \
  --exclude-table=public.alembic_version > "${DATA_BACKUP}"

echo "Recreating public schema"
docker exec -i "${POSTGRES_CONTAINER}" psql \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  -v ON_ERROR_STOP=1 <<SQL
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public AUTHORIZATION ${POSTGRES_USER};
GRANT ALL ON SCHEMA public TO ${POSTGRES_USER};
GRANT CREATE, USAGE ON SCHEMA public TO ${POSTGRES_USER};
SQL

echo "Applying Alembic baseline"
docker compose -f "${ROOT_DIR}/docker-compose.backend.yml" run --rm --entrypoint alembic \
  ai-runtime -c /app/db/alembic.ini upgrade head

echo "Restoring application data"
docker exec -i "${POSTGRES_CONTAINER}" pg_restore \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --data-only \
  --disable-triggers \
  --no-owner \
  --no-privileges < "${DATA_BACKUP}"

echo "Database reset to Alembic completed"
echo "Backups kept under ${BACKUP_DIR}"
