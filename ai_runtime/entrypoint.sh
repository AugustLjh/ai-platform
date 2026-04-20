#!/bin/bash
set -euo pipefail

echo "Waiting for PostgreSQL to be ready..."
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is up - applying Alembic migrations..."
alembic -c /app/db/alembic.ini upgrade head

echo "Alembic migration complete - starting AI Runtime..."
exec "$@"
