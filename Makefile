.PHONY: help dev prod build clean logs test

# 默认目标
help:
	@echo "AI Platform - Docker Compose 管理命令"
	@echo ""
	@echo "开发环境:"
	@echo "  make dev          - 启动开发环境（支持热重载）"
	@echo "  make dev-build    - 重新构建并启动开发环境"
	@echo "  make dev-logs     - 查看开发环境日志"
	@echo "  make dev-down     - 停止开发环境"
	@echo ""
	@echo "生产环境:"
	@echo "  make prod         - 启动生产环境"
	@echo "  make prod-build   - 重新构建并启动生产环境"
	@echo "  make prod-logs    - 查看生产环境日志"
	@echo "  make prod-down    - 停止生产环境"
	@echo ""
	@echo "通用命令:"
	@echo "  make clean        - 清理所有容器和卷"
	@echo "  make ps           - 查看运行中的容器"
	@echo "  make test         - 运行测试"

# ============================================
# 开发环境命令
# ============================================

dev:
	@echo "启动开发环境（支持热重载）..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile full up -d
	@echo "开发环境已启动！"
	@echo "  - 前端: http://localhost:5173 (Vite 热重载)"
	@echo "  - 后端: http://localhost:8080"
	@echo "  - AI Runtime: http://localhost:8000"
	@echo "  - PostgreSQL: localhost:5433"
	@echo "  - Redis: localhost:6379"
	@echo "  - Elasticsearch: http://localhost:9200"

dev-build:
	@echo "重新构建并启动开发环境..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile full up -d --build

dev-logs:
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

dev-down:
	@echo "停止开发环境..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile full down

# ============================================
# 生产环境命令
# ============================================

prod:
	@echo "启动生产环境..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile full up -d
	@echo "生产环境已启动！"
	@echo "  - 访问: http://localhost"
	@echo "  - HTTPS: https://localhost (需配置域名和证书)"

prod-build:
	@echo "重新构建并启动生产环境..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile full up -d --build

prod-logs:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

prod-down:
	@echo "停止生产环境..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile full down

# ============================================
# 通用命令
# ============================================

ps:
	docker-compose ps

clean:
	@echo "清理所有容器、网络和卷..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile full down -v
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile full down -v
	@echo "清理完成！"

test:
	@echo "运行测试..."
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml run --rm ai-runtime pytest
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml run --rm platform go test ./...

# ============================================
# 数据库管理
# ============================================

db-migrate:
	@echo "运行数据库迁移..."
	docker-compose exec postgres psql -U ai_platform -d ai_platform -f /docker-entrypoint-initdb.d/001_initial_schema.sql
	docker-compose exec postgres psql -U ai_platform -d ai_platform -f /docker-entrypoint-initdb.d/002_knowledge_base_enhancements.sql
	docker-compose exec postgres psql -U ai_platform -d ai_platform -f /docker-entrypoint-initdb.d/004_add_knowledge_bases.sql
	docker-compose exec postgres psql -U ai_platform -d ai_platform -f /docker-entrypoint-initdb.d/005_migrate_existing_documents.sql
	docker-compose exec postgres psql -U ai_platform -d ai_platform -f /docker-entrypoint-initdb.d/006_llm_models.sql
	# 可选：启用pgvector
	docker-compose exec postgres psql -U ai_platform -d ai_platform -f /docker-entrypoint-initdb.d/003_enable_pgvector.sql

db-shell:
	@echo "连接到 PostgreSQL..."
	docker-compose exec postgres psql -U ai_platform -d ai_platform

redis-cli:
	@echo "连接到 Redis..."
	docker-compose exec redis redis-cli

# ============================================
# 服务管理
# ============================================

restart-platform:
	docker-compose restart platform

restart-ai-runtime:
	docker-compose restart ai-runtime

restart-frontend:
	docker-compose restart frontend

restart-nginx:
	docker-compose restart nginx
