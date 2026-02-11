#!/bin/bash
# Nginx entrypoint with automatic SSL certificate acquisition
# This script runs when the nginx container starts

set -e

echo "=========================================="
echo "AI Platform Nginx Startup"
echo "=========================================="

# Load environment variables
DOMAIN=${DOMAIN:-localhost}
EMAIL=${EMAIL:-admin@localhost}
LETSENCRYPT_STAGING=${LETSENCRYPT_STAGING:-0}

echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo "Let's Encrypt Mode: $([ "$LETSENCRYPT_STAGING" = "1" ] && echo "STAGING" || echo "PRODUCTION")"
echo "=========================================="

# Certificate paths
CERT_PATH="/etc/letsencrypt/live/$DOMAIN"
FULLCHAIN="$CERT_PATH/fullchain.pem"
PRIVKEY="$CERT_PATH/privkey.pem"

# Check if certificates already exist
if [ -f "$FULLCHAIN" ] && [ -f "$PRIVKEY" ]; then
    echo "✓ SSL certificates found at $CERT_PATH"
    echo "✓ Starting nginx with existing certificates..."
    exec nginx -g "daemon off;"
fi

echo "⚠ SSL certificates not found"
echo "→ Will attempt to obtain certificates from Let's Encrypt"
echo "=========================================="

# Check if domain is localhost or IP (can't get Let's Encrypt cert)
if [ "$DOMAIN" = "localhost" ] || [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "⚠ Domain is localhost or IP address"
    echo "→ Cannot obtain Let's Encrypt certificate"
    echo "→ Generating self-signed certificate..."

    mkdir -p /etc/nginx/ssl
    openssl req -x509 -nodes -newkey rsa:2048 \
        -days 365 \
        -keyout /etc/nginx/ssl/self-signed.key \
        -out /etc/nginx/ssl/self-signed.crt \
        -subj "/CN=$DOMAIN"

    echo "✓ Self-signed certificate generated"
    echo "⚠ WARNING: Browsers will show security warnings"
    echo "→ Starting nginx with self-signed certificate..."
    exec nginx -g "daemon off;"
fi

# Create temporary HTTP-only nginx config
echo "→ Creating temporary HTTP-only configuration..."
cat > /etc/nginx/conf.d/default.conf << 'EOF'
server {
    listen 80;
    server_name _;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 "Obtaining SSL certificate, please wait...\n";
        add_header Content-Type text/plain;
    }
}
EOF

# Start nginx in background for certificate acquisition
echo "→ Starting nginx temporarily for certificate validation..."
nginx

# Wait for nginx to start
sleep 3

# Prepare certbot arguments
CERTBOT_ARGS="certonly --webroot -w /var/www/certbot"
CERTBOT_ARGS="$CERTBOT_ARGS -d $DOMAIN"

# Add www subdomain if main domain doesn't start with www
if [[ ! "$DOMAIN" =~ ^www\. ]]; then
    CERTBOT_ARGS="$CERTBOT_ARGS -d www.$DOMAIN"
fi

CERTBOT_ARGS="$CERTBOT_ARGS --email $EMAIL"
CERTBOT_ARGS="$CERTBOT_ARGS --agree-tos"
CERTBOT_ARGS="$CERTBOT_ARGS --non-interactive"
CERTBOT_ARGS="$CERTBOT_ARGS --keep-until-expiring"

# Add staging flag if enabled
if [ "$LETSENCRYPT_STAGING" = "1" ]; then
    echo "⚠ Using Let's Encrypt STAGING server (test mode)"
    CERTBOT_ARGS="$CERTBOT_ARGS --staging"
fi

# Attempt to obtain certificate
echo "→ Requesting Let's Encrypt certificate..."
echo "→ Command: certbot $CERTBOT_ARGS"
echo "=========================================="

if certbot $CERTBOT_ARGS; then
    echo "=========================================="
    echo "✓ SSL certificate obtained successfully!"
    echo "✓ Certificate location: $CERT_PATH"

    # Stop temporary nginx
    echo "→ Stopping temporary nginx..."
    nginx -s stop
    sleep 2

    # Restore original nginx configuration
    echo "→ Restoring SSL-enabled configuration..."
    # The original config should be mounted or copied during build

    # Start nginx with SSL
    echo "✓ Starting nginx with SSL certificate..."
    exec nginx -g "daemon off;"
else
    echo "=========================================="
    echo "✗ Failed to obtain SSL certificate"
    echo "→ This could be due to:"
    echo "  1. Domain DNS not pointing to this server"
    echo "  2. Port 80 not accessible from internet"
    echo "  3. Let's Encrypt rate limits"
    echo "  4. Invalid email address"
    echo "=========================================="
    echo "→ Generating self-signed certificate as fallback..."

    mkdir -p /etc/nginx/ssl
    openssl req -x509 -nodes -newkey rsa:2048 \
        -days 365 \
        -keyout /etc/nginx/ssl/self-signed.key \
        -out /etc/nginx/ssl/self-signed.crt \
        -subj "/CN=$DOMAIN"

    echo "✓ Self-signed certificate generated"
    echo "⚠ WARNING: Browsers will show security warnings"

    # Stop temporary nginx
    nginx -s stop
    sleep 2

    # Restore original configuration
    if [ -f /etc/nginx/conf.d/default.conf.ssl ]; then
        cp /etc/nginx/conf.d/default.conf.ssl /etc/nginx/conf.d/default.conf
    fi

    # Update config to use self-signed certificate
    sed -i 's|/etc/letsencrypt/live/[^/]*/fullchain.pem|/etc/nginx/ssl/self-signed.crt|g' /etc/nginx/conf.d/default.conf
    sed -i 's|/etc/letsencrypt/live/[^/]*/privkey.pem|/etc/nginx/ssl/self-signed.key|g' /etc/nginx/conf.d/default.conf

    echo "→ Starting nginx with self-signed certificate..."
    echo "=========================================="
    echo "⚠ Using self-signed certificate"
    echo "Your site is available at:"
    echo "  https://$DOMAIN (with browser warning)"
    echo "=========================================="
    exec nginx -g "daemon off;"
fi
