#!/bin/bash

# Database initialization script for AI Platform

echo "======================================"
echo "AI Platform - Database Setup"
echo "======================================"
echo ""

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose is not installed"
    exit 1
fi

# Start only database services
echo "Starting database services..."
docker-compose up -d postgres redis elasticsearch

echo ""
echo "Waiting for databases to be ready..."
sleep 10

# Check PostgreSQL
echo "Checking PostgreSQL..."
docker-compose exec -T postgres pg_isready -U ai_platform
if [ $? -eq 0 ]; then
    echo "✓ PostgreSQL is ready"
else
    echo "✗ PostgreSQL is not ready"
fi

# Check Redis
echo "Checking Redis..."
docker-compose exec -T redis redis-cli ping
if [ $? -eq 0 ]; then
    echo "✓ Redis is ready"
else
    echo "✗ Redis is not ready"
fi

# Check Elasticsearch
echo "Checking Elasticsearch..."
docker-compose exec -T elasticsearch curl -s http://localhost:9200/_cluster/health > /dev/null
if [ $? -eq 0 ]; then
    echo "✓ Elasticsearch is ready"
else
    echo "✗ Elasticsearch is not ready"
fi

echo ""
echo "======================================"
echo "Database Services Status:"
echo "======================================"
docker-compose ps postgres redis elasticsearch

echo ""
echo "======================================"
echo "Connection Information:"
echo "======================================"
echo ""
echo "PostgreSQL:"
echo "  Host: localhost (or 'postgres' within Docker network)"
echo "  Port: 5432 (only accessible from other containers)"
echo "  Database: ai_platform"
echo "  User: ai_platform"
echo "  Password: 19980912"
echo "  Connection String: postgresql://ai_platform:19980912@postgres:5432/ai_platform"
echo ""
echo "Redis:"
echo "  Host: localhost (or 'redis' within Docker network)"
echo "  Port: 6379 (only accessible from other containers)"
echo "  Connection String: redis://redis:6379/0"
echo ""
echo "Elasticsearch:"
echo "  Host: localhost (or 'elasticsearch' within Docker network)"
echo "  Port: 9200 (only accessible from other containers)"
echo "  URL: http://elasticsearch:9200"
echo ""
echo "Kibana (optional):"
echo "  To start: docker-compose --profile observability up -d kibana"
echo "  URL: http://localhost:5601"
echo ""
echo "======================================"
echo "Setup Complete!"
echo "======================================"
