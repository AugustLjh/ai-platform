#!/bin/bash
# Check SSL certificate status

set -e

# Load environment
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

DOMAIN=${DOMAIN:-localhost}

echo "==================================="
echo "SSL Certificate Status"
echo "==================================="

# Check if certificate exists
if docker-compose exec nginx test -d "/etc/letsencrypt/live/$DOMAIN" 2>/dev/null; then
    echo "Certificate found for: $DOMAIN"
    echo ""

    # Show certificate details
    docker-compose exec nginx certbot certificates

    echo ""
    echo "==================================="

    # Check expiration
    docker-compose exec nginx openssl x509 \
        -in "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" \
        -noout -dates
else
    echo "No certificate found for: $DOMAIN"
    echo "Run: ./scripts/setup-ssl.sh"
fi

echo "==================================="
