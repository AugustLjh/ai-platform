COMPOSE := docker compose
DEV_FILES := -f docker-compose.yml -f docker-compose.dev.yml
PROD_INFRA_FILES := -f docker-compose.infra.yml
PROD_BACKEND_FILES := -f docker-compose.backend.yml
PROD_FRONTEND_FILES := -f docker-compose.frontend.yml

.PHONY: help \
	dev dev-build dev-logs dev-down \
	prod prod-build prod-logs prod-down \
	infra-up infra-build infra-logs infra-down infra-ps \
	backend-up backend-build backend-logs backend-down backend-ps \
	frontend-up frontend-build frontend-logs frontend-down frontend-ps \
	ps clean test \
	db-migrate db-shell redis-cli \
	restart-platform restart-ai-runtime restart-frontend restart-nginx

help:
	@echo "AI Platform - Docker Compose 管理命令"
	@echo ""
	@echo "开发环境:"
	@echo "  make dev              - 启动开发环境（热重载）"
	@echo "  make dev-build        - 重新构建并启动开发环境"
	@echo "  make dev-logs         - 查看开发环境日志"
	@echo "  make dev-down         - 停止开发环境"
	@echo ""
	@echo "拆分后的生产编排:"
	@echo "  make infra-up         - 启动基础设施（postgres/redis/es/nginx/certbot）"
	@echo "  make infra-build      - 重构基础设施中的可构建镜像（当前为 nginx）"
	@echo "  make infra-logs       - 查看基础设施日志"
	@echo "  make infra-down       - 停止基础设施"
	@echo "  make backend-up       - 启动后端（ai-runtime/platform）"
	@echo "  make backend-build    - 重构后端镜像"
	@echo "  make backend-logs     - 查看后端日志"
	@echo "  make backend-down     - 停止后端"
	@echo "  make frontend-up      - 启动前端"
	@echo "  make frontend-build   - 重构前端镜像"
	@echo "  make frontend-logs    - 查看前端日志"
	@echo "  make frontend-down    - 停止前端"
	@echo ""
	@echo "兼容的整栈命令:"
	@echo "  make prod             - 依次启动 infra/backend/frontend"
	@echo "  make prod-build       - 依次重构并启动 infra/backend/frontend"
	@echo "  make prod-logs        - 提示使用拆分日志命令"
	@echo "  make prod-down        - 按 frontend/backend/infra 顺序停止"
	@echo ""
	@echo "通用命令:"
	@echo "  make ps               - 查看 ai-platform 相关容器"
	@echo "  make clean            - 停止开发环境和拆分后的生产环境，并清理卷"
	@echo "  make test             - 在开发编排中执行测试"
	@echo ""
	@echo "数据库与服务:"
	@echo "  make db-migrate       - 向 postgres 容器顺序执行迁移"
	@echo "  make db-shell         - 进入 PostgreSQL shell"
	@echo "  make redis-cli        - 进入 Redis CLI"
	@echo "  make restart-platform - 重启 platform"
	@echo "  make restart-ai-runtime - 重启 ai-runtime"
	@echo "  make restart-frontend - 重启 frontend"
	@echo "  make restart-nginx    - 重启 nginx"

# ============================================
# 开发环境
# ============================================

dev:
	@echo "启动开发环境（支持热重载）..."
	$(COMPOSE) $(DEV_FILES) --profile full up -d
	@echo "开发环境已启动"
	@echo "  - 前端: http://localhost:5173"
	@echo "  - 后端: http://localhost:8080"
	@echo "  - AI Runtime: http://localhost:8000"
	@echo "  - PostgreSQL: localhost:5433"
	@echo "  - Redis: localhost:6379"
	@echo "  - Elasticsearch: http://localhost:9200"

dev-build:
	@echo "重新构建并启动开发环境..."
	$(COMPOSE) $(DEV_FILES) --profile full up -d --build

dev-logs:
	$(COMPOSE) $(DEV_FILES) logs -f

dev-down:
	@echo "停止开发环境..."
	$(COMPOSE) $(DEV_FILES) --profile full down --remove-orphans

# ============================================
# 拆分后的生产编排
# ============================================

infra-up:
	@echo "启动基础设施..."
	$(COMPOSE) $(PROD_INFRA_FILES) up -d

infra-build:
	@echo "重构基础设施镜像（当前仅 nginx 需要 build）..."
	$(COMPOSE) $(PROD_INFRA_FILES) build nginx
	$(COMPOSE) $(PROD_INFRA_FILES) up -d nginx

infra-logs:
	$(COMPOSE) $(PROD_INFRA_FILES) logs -f postgres redis elasticsearch nginx certbot

infra-down:
	@echo "停止基础设施..."
	$(COMPOSE) $(PROD_INFRA_FILES) down --remove-orphans

infra-ps:
	$(COMPOSE) $(PROD_INFRA_FILES) ps

backend-up:
	@echo "启动后端服务..."
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d

backend-build:
	@echo "重构后端镜像..."
	$(COMPOSE) $(PROD_BACKEND_FILES) build ai-runtime platform
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d ai-runtime platform

backend-logs:
	$(COMPOSE) $(PROD_BACKEND_FILES) logs -f ai-runtime platform

backend-down:
	@echo "停止后端服务..."
	$(COMPOSE) $(PROD_BACKEND_FILES) down --remove-orphans

backend-ps:
	$(COMPOSE) $(PROD_BACKEND_FILES) ps

frontend-up:
	@echo "启动前端服务..."
	$(COMPOSE) $(PROD_FRONTEND_FILES) up -d

frontend-build:
	@echo "重构前端镜像..."
	$(COMPOSE) $(PROD_FRONTEND_FILES) build frontend
	$(COMPOSE) $(PROD_FRONTEND_FILES) up -d frontend

frontend-logs:
	$(COMPOSE) $(PROD_FRONTEND_FILES) logs -f frontend

frontend-down:
	@echo "停止前端服务..."
	$(COMPOSE) $(PROD_FRONTEND_FILES) down --remove-orphans

frontend-ps:
	$(COMPOSE) $(PROD_FRONTEND_FILES) ps

# ============================================
# 兼容的整栈命令
# ============================================

prod: infra-up backend-up frontend-up
	@echo "生产环境已按 infra/backend/frontend 拆分方式启动"
	@echo "  - HTTP: http://localhost"
	@echo "  - 后端 API: http://localhost:8080"
	@echo "  - AI Runtime: http://localhost:8000"

prod-build: infra-build backend-build frontend-build
	@echo "生产环境镜像已按拆分方式重构并启动"

prod-logs:
	@echo "生产日志已拆分，请使用以下命令："
	@echo "  make infra-logs"
	@echo "  make backend-logs"
	@echo "  make frontend-logs"

prod-down: frontend-down backend-down infra-down
	@echo "生产环境已按 frontend/backend/infra 顺序停止"

# ============================================
# 通用命令
# ============================================

ps:
	docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" --filter name=ai-platform

clean:
	@echo "清理开发环境和拆分后的生产环境..."
	-$(COMPOSE) $(DEV_FILES) --profile full down -v --remove-orphans
	-$(COMPOSE) $(PROD_FRONTEND_FILES) down -v --remove-orphans
	-$(COMPOSE) $(PROD_BACKEND_FILES) down -v --remove-orphans
	-$(COMPOSE) $(PROD_INFRA_FILES) down -v --remove-orphans
	@echo "清理完成"

test:
	@echo "运行测试..."
	$(COMPOSE) $(DEV_FILES) run --rm ai-runtime pytest
	$(COMPOSE) $(DEV_FILES) run --rm platform go test ./...

# ============================================
# 数据库与缓存
# ============================================

db-migrate:
	@echo "执行数据库迁移..."
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/001_initial_schema.sql
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/002_knowledge_base_enhancements.sql
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/003_enable_pgvector.sql
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/004_add_knowledge_bases.sql
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/005_migrate_existing_documents.sql
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/006_llm_models.sql
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/007_add_model_type.sql
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/008_add_quota_periods.sql
	docker compose $(PROD_INFRA_FILES) exec -T postgres psql -U ai_platform -d ai_platform < db/migrations/009_add_retrieval_evaluation.sql

db-shell:
	@echo "连接到 PostgreSQL..."
	$(COMPOSE) $(PROD_INFRA_FILES) exec postgres psql -U ai_platform -d ai_platform

redis-cli:
	@echo "连接到 Redis..."
	$(COMPOSE) $(PROD_INFRA_FILES) exec redis redis-cli

# ============================================
# 服务重启
# ============================================

restart-platform:
	$(COMPOSE) $(PROD_BACKEND_FILES) restart platform

restart-ai-runtime:
	$(COMPOSE) $(PROD_BACKEND_FILES) restart ai-runtime

restart-frontend:
	$(COMPOSE) $(PROD_FRONTEND_FILES) restart frontend

restart-nginx:
	$(COMPOSE) $(PROD_INFRA_FILES) restart nginx
