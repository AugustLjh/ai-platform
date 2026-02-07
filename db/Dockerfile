FROM pgvector/pgvector:pg16

# Copy database migration scripts into the container
# These will be executed automatically on first startup
COPY migrations/*.sql /docker-entrypoint-initdb.d/

# Ensure scripts are executable
RUN chmod -R 755 /docker-entrypoint-initdb.d/
