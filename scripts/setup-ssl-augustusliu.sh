#!/bin/bash
# Setup SSL certificates for augustusliu.top using Let's Encrypt

set -e

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                                                                      ║"
echo "║           Let's Encrypt SSL Setup for augustusliu.top               ║"
echo "║                                                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "❌ Error: .env file not found"
    exit 1
fi

# Validate required variables
if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "❌ Error: DOMAIN and EMAIL must be set in .env"
    exit 1
fi

echo "📋 Configuration:"
echo "   Domain: $DOMAIN"
echo "   Email: $EMAIL"
echo "   Mode: $([ "$LETSENCRYPT_STAGING" = "1" ] && echo "STAGING (Testing)" || echo "PRODUCTION (Real Certificate)")"
echo ""

# Check if running in staging mode
if [ "$LETSENCRYPT_STAGING" = "1" ]; then
    echo "⚠️  WARNING: Running in STAGING mode"
    echo "   Certificates will NOT be trusted by browsers"
    echo "   This is for testing only"
    echo ""
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Starting base services..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker-compose up -d postgres redis ai-runtime platform frontend

echo "✅ Base services started"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Waiting for services to be ready..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sleep 30

echo "✅ Services should be ready"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Generating temporary self-signed certificate..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create temporary self-signed certificate for initial nginx start
mkdir -p nginx/ssl
openssl req -x509 -nodes -newkey rsa:2048 \
    -days 1 \
    -keyout nginx/ssl/temp-self-signed.key \
    -out nginx/ssl/temp-self-signed.crt \
    -subj "/CN=$DOMAIN" 2>/dev/null

# Temporarily update nginx config to use self-signed cert
cp nginx/conf.d/default.conf nginx/conf.d/default.conf.backup
sed -i.tmp 's|ssl_certificate /etc/nginx/ssl/self-signed.crt;|ssl_certificate /etc/nginx/ssl/temp-self-signed.crt;|g' nginx/conf.d/default.conf
sed -i.tmp 's|ssl_certificate_key /etc/nginx/ssl/self-signed.key;|ssl_certificate_key /etc/nginx/ssl/temp-self-signed.key;|g' nginx/conf.d/default.conf

echo "✅ Temporary certificate created"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Starting nginx..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker-compose up -d nginx

echo "✅ Nginx started with temporary certificate"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 5: Waiting for nginx to be ready..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

sleep 10

echo "✅ Nginx should be ready"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 6: Requesting Let's Encrypt certificate..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Build certbot command
CERTBOT_ARGS="certonly --webroot -w /var/www/certbot -d $DOMAIN --email $EMAIL --agree-tos --non-interactive"

if [ "$LETSENCRYPT_STAGING" = "1" ]; then
    echo "🧪 Using Let's Encrypt STAGING server (for testing)"
    CERTBOT_ARGS="$CERTBOT_ARGS --staging"
else
    echo "🔐 Using Let's Encrypt PRODUCTION server (real certificate)"
fi

# Request certificate
docker-compose run --rm certbot $CERTBOT_ARGS

if [ $? -eq 0 ]; then
    echo "✅ Certificate obtained successfully!"
else
    echo "❌ Certificate request failed"
    echo "   Check the error messages above"
    echo "   Common issues:"
    echo "   - DNS not pointing to this server"
    echo "   - Port 80 not accessible from internet"
    echo "   - Rate limit exceeded (use LETSENCRYPT_STAGING=1 for testing)"
    exit 1
fi

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 7: Updating nginx configuration..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create SSL configuration with Let's Encrypt certificate
cat > nginx/conf.d/ssl.conf << EOF
# HTTPS Server with Let's Encrypt for augustusliu.top
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name augustusliu.top;

    # Let's Encrypt certificates
    ssl_certificate /etc/letsencrypt/live/augustusliu.top/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/augustusliu.top/privkey.pem;

    # SSL configuration
    include /etc/nginx/ssl/options-ssl-nginx.conf;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self' https:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';" always;

    # Root location - proxy to frontend
    location / {
        proxy_pass http://frontend_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # API endpoints - proxy to platform
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        limit_conn conn_limit 10;

        proxy_pass http://platform_backend/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # SSE/WebSocket support
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
        proxy_request_buffering off;

        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # Login endpoint - stricter rate limiting
    location /api/v1/auth/login {
        limit_req zone=login_limit burst=3 nodelay;

        proxy_pass http://platform_backend/api/v1/auth/login;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }

    # Deny access to hidden files
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
EOF

echo "✅ SSL configuration created"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 8: Reloading nginx with Let's Encrypt certificate..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Test nginx configuration
docker-compose exec nginx nginx -t

if [ $? -eq 0 ]; then
    # Reload nginx
    docker-compose exec nginx nginx -s reload
    echo "✅ Nginx reloaded with Let's Encrypt certificate"
else
    echo "❌ Nginx configuration test failed"
    exit 1
fi

echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 9: Starting certbot auto-renewal service..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

docker-compose up -d certbot

echo "✅ Certbot auto-renewal service started"
echo ""

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                                                                      ║"
echo "║                    🎉 SSL Setup Complete! 🎉                         ║"
echo "║                                                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "✅ Your site is now available at:"
echo "   🌐 https://augustusliu.top"
echo ""
echo "📋 Certificate details:"
echo "   Domain: augustusliu.top"
echo "   Issuer: Let's Encrypt"
echo "   Auto-renewal: Every 12 hours (via certbot service)"
echo ""
echo "🔍 Next steps:"
echo "   1. Test your site: https://augustusliu.top"
echo "   2. Check certificate: ./scripts/check-ssl.sh"
echo "   3. Test SSL rating: https://www.ssllabs.com/ssltest/"
echo ""
echo "📚 Useful commands:"
echo "   - Check certificate: ./scripts/check-ssl.sh"
echo "   - Backup certificate: ./scripts/backup-certs.sh"
echo "   - View logs: docker-compose logs nginx certbot"
echo ""
