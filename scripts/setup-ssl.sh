#!/bin/bash
# Setup SSL certificates for production

set -e

echo "==================================="
echo "AI Platform SSL Setup"
echo "==================================="

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "Error: .env file not found"
    exit 1
fi

# Validate required variables
if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "Error: DOMAIN and EMAIL must be set in .env"
    exit 1
fi

echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "==================================="

# Check if running in staging mode
if [ "$LETSENCRYPT_STAGING" = "1" ]; then
    echo "WARNING: Running in STAGING mode"
    echo "Certificates will NOT be trusted by browsers"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Start services (except nginx)
echo "Starting services..."
docker-compose up -d postgres redis ai-runtime platform frontend

# Wait for services to be healthy
echo "Waiting for services to be ready..."
sleep 30

# Generate self-signed certificate for initial nginx start
echo "Generating self-signed certificate..."
docker-compose run --rm nginx sh -c "
    mkdir -p /etc/nginx/ssl
    openssl req -x509 -nodes -newkey rsa:2048 \
        -days 1 \
        -keyout /etc/nginx/ssl/self-signed.key \
        -out /etc/nginx/ssl/self-signed.crt \
        -subj '/CN=$DOMAIN'
"

# Start nginx with self-signed cert
echo "Starting nginx..."
docker-compose up -d nginx

# Wait for nginx to start
sleep 10

# Request Let's Encrypt certificate
echo "Requesting Let's Encrypt certificate..."
CERTBOT_ARGS="--nginx -d $DOMAIN --email $EMAIL --agree-tos --non-interactive"

if [ "$LETSENCRYPT_STAGING" = "1" ]; then
    echo "Using Let's Encrypt staging server (for testing)"
    CERTBOT_ARGS="$CERTBOT_ARGS --staging"
fi

docker-compose exec nginx certbot $CERTBOT_ARGS

# Start certbot auto-renewal service
echo "Starting certbot auto-renewal..."
docker-compose up -d certbot

echo "==================================="
echo "SSL Setup Complete!"
echo "==================================="
echo "Your site should now be available at:"
echo "  https://$DOMAIN"
echo ""
echo "Certificate will auto-renew every 12 hours"
echo "==================================="
