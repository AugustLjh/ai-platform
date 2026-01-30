#!/bin/bash
# Backup SSL certificates

set -e

BACKUP_DIR="./backups/ssl"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/letsencrypt_$TIMESTAMP.tar.gz"

echo "==================================="
echo "SSL Certificate Backup"
echo "==================================="

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup Let's Encrypt directory
echo "Creating backup..."
docker run --rm \
    -v ai-platform_letsencrypt_data:/letsencrypt \
    -v "$(pwd)/$BACKUP_DIR:/backup" \
    alpine \
    tar czf "/backup/letsencrypt_$TIMESTAMP.tar.gz" -C / letsencrypt

# Verify backup
if [ -f "$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "Backup created: $BACKUP_FILE ($SIZE)"

    # Keep only last 7 backups
    echo "Cleaning old backups..."
    ls -t "$BACKUP_DIR"/letsencrypt_*.tar.gz | tail -n +8 | xargs -r rm

    echo "Remaining backups:"
    ls -lh "$BACKUP_DIR"/letsencrypt_*.tar.gz
else
    echo "Error: Backup failed"
    exit 1
fi

echo "==================================="
echo "Backup complete!"
echo "==================================="
