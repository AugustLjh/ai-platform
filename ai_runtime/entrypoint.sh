#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is up - checking for migrations..."
# Wait for knowledge_bases table to exist (created by migration 004)
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt knowledge_bases' 2>/dev/null | grep -q knowledge_bases; do
  echo "Waiting for migrations to complete..."
  sleep 2
done

echo "Migrations complete - starting AI Runtime..."
exec "$@"
