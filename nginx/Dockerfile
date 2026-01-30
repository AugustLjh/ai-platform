FROM nginx:alpine

# Install certbot for Let's Encrypt
RUN apk add --no-cache \
    certbot \
    certbot-nginx \
    openssl \
    bash

# Create directories
RUN mkdir -p /etc/nginx/ssl \
    && mkdir -p /var/www/certbot \
    && mkdir -p /etc/letsencrypt

# Generate dhparam (2048 bit for faster generation, use 4096 in production)
RUN openssl dhparam -out /etc/nginx/ssl/dhparam.pem 2048

# Copy nginx configurations
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/
COPY ssl/options-ssl-nginx.conf /etc/nginx/ssl/options-ssl-nginx.conf

# Copy certificate renewal script
COPY scripts/renew-certs.sh /usr/local/bin/renew-certs.sh
RUN chmod +x /usr/local/bin/renew-certs.sh

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
