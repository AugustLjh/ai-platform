#!/bin/bash
# Certificate renewal script for Let's Encrypt

set -e

echo "[$(date)] Starting certificate renewal check..."

# Renew certificates (certbot will only renew if needed)
certbot renew --nginx --non-interactive --quiet

# Check if renewal happened
if [ $? -eq 0 ]; then
    echo "[$(date)] Certificate renewal check completed"

    # Reload nginx to apply new certificates
    nginx -t && nginx -s reload
    echo "[$(date)] Nginx reloaded"
else
    echo "[$(date)] Certificate renewal failed"
    exit 1
fi

echo "[$(date)] Certificate renewal process finished"
