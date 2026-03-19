COMPOSE := docker compose
PROD_INFRA_FILES := -f docker-compose.infra.yml
PROD_BACKEND_FILES := -f docker-compose.backend.yml
PROD_FRONTEND_FILES := -f docker-compose.frontend.yml
SAFE_BUILD_ENV := DOCKER_BUILDKIT=0 COMPOSE_PARALLEL_LIMIT=1
FRONTEND_RELEASE_ROOT := frontend-dist
PROD_REQUIRED_IMAGES := \
	postgres:16 \
	docker.1ms.run/library/redis:alpine \
	qdrant/qdrant:latest \
	ai-platform-infra-nginx \
	certbot/certbot:latest \
	ai-platform-backend-ai-runtime \
	ai-platform-backend-platform

.PHONY: help \
	prod prod-build prod-build-safe prod-logs prod-down prod-check \
	infra-up infra-build infra-build-safe infra-logs infra-down infra-ps \
	backend-up backend-build backend-build-safe backend-logs backend-down backend-ps \
	frontend-up frontend-build frontend-build-safe frontend-logs frontend-down frontend-ps \
	ai-runtime-up ai-runtime-build ai-runtime-build-safe ai-runtime-down \
	api-up api-build api-build-safe api-down \
	platform-up platform-build platform-build-safe platform-down \
	ps clean test \
	db-upgrade db-current db-history db-revision db-reset-to-alembic db-shell redis-cli qdrant-backfill \
	restart-platform restart-ai-runtime restart-frontend restart-nginx

help:
	@echo "AI Platform - Docker Compose 管理命令"
	@echo ""
	@echo "统一部署编排:"
	@echo "  make infra-up         - 启动基础设施（postgres/redis/qdrant/nginx/certbot）"
	@echo "  make infra-build      - 重构基础设施中的可构建镜像"
	@echo "  make infra-build-safe - 低 I/O 模式重构 nginx 镜像"
	@echo "  make infra-logs       - 查看基础设施日志"
	@echo "  make infra-down       - 停止基础设施"
	@echo "  make backend-up       - 启动后端（ai-runtime/platform）"
	@echo "  make backend-build    - 重构后端镜像"
	@echo "  make backend-build-safe - 低 I/O 模式重构后端镜像"
	@echo "  make backend-logs     - 查看后端日志"
	@echo "  make backend-down     - 停止后端"
	@echo "  make frontend-up      - 校验当前前端静态发布并确保 nginx 运行"
	@echo "  make frontend-build   - 构建并发布新的前端静态版本"
	@echo "  make frontend-build-safe - 低 I/O 模式构建并发布新的前端静态版本"
	@echo "  make frontend-logs    - 查看共享 nginx 日志"
	@echo "  make frontend-down    - 前端已并入共享 nginx，无独立容器可停止"
	@echo ""
	@echo "单服务重构:"
	@echo "  make ai-runtime-up    - 仅启动 AI Runtime 服务"
	@echo "  make ai-runtime-build - 仅重构 AI Runtime 镜像"
	@echo "  make ai-runtime-build-safe - 低 I/O 模式仅重构 AI Runtime 镜像"
	@echo "  make ai-runtime-down  - 仅停止并移除 AI Runtime 服务容器"
	@echo "  make api-up           - 仅启动 API 服务（platform）"
	@echo "  make api-build        - 仅重构 API 镜像（platform）"
	@echo "  make api-build-safe   - 低 I/O 模式仅重构 API 镜像（platform）"
	@echo "  make api-down         - 仅停止并移除 API 服务容器（platform）"
	@echo "  make platform-up      - 兼容别名，等同于 make api-up"
	@echo "  make platform-build   - 兼容别名，等同于 make api-build"
	@echo "  make platform-build-safe - 兼容别名，等同于 make api-build-safe"
	@echo "  make platform-down    - 兼容别名，等同于 make api-down"
	@echo ""
	@echo "兼容的整栈命令:"
	@echo "  make prod-check       - 检查 prod 所需镜像和高资源配置"
	@echo "  make prod             - 安全启动 infra/backend/frontend（禁止隐式 build）"
	@echo "  make prod-build       - 依次重构并启动 infra/backend/frontend"
	@echo "  make prod-build-safe  - 低 I/O 模式依次重构并启动 infra/backend/frontend"
	@echo "  make prod-logs        - 提示使用拆分日志命令"
	@echo "  make prod-down        - 按 frontend/backend/infra 顺序停止"
	@echo ""
	@echo "通用命令:"
	@echo "  make ps               - 查看 ai-platform 相关容器"
	@echo "  make clean            - 停止当前统一部署环境，并清理卷"
	@echo "  make test             - 在本地开发环境执行测试"
	@echo ""
	@echo "数据库与服务:"
	@echo "  make db-upgrade       - 使用 Alembic 升级到最新版本"
	@echo "  make db-current       - 查看当前 Alembic 版本"
	@echo "  make db-history       - 查看 Alembic 历史"
	@echo "  make db-revision m=... - 创建新的 Alembic revision"
	@echo "  make db-reset-to-alembic - 备份数据并重建为 Alembic 管理"
	@echo "  make db-shell         - 进入 PostgreSQL shell"
	@echo "  make redis-cli        - 进入 Redis CLI"
	@echo "  make qdrant-backfill  - 在 ai-runtime 容器内执行 Qdrant 全量回填"
	@echo "  make restart-platform - 重启 platform"
	@echo "  make restart-ai-runtime - 重启 ai-runtime"
	@echo "  make restart-frontend - 前端已并入共享 nginx，重新发布请使用 make frontend-build"
	@echo "  make restart-nginx    - 重启 nginx"

# ============================================
# 拆分后的生产编排
# ============================================

infra-up:
	@echo "启动基础设施..."
	$(COMPOSE) $(PROD_INFRA_FILES) up -d --no-build

infra-build:
	@echo "重构基础设施镜像..."
	$(COMPOSE) $(PROD_INFRA_FILES) build 
	$(COMPOSE) $(PROD_INFRA_FILES) up -d 

infra-build-safe:
	@echo "低 I/O 模式重构基础设施镜像（当前仅 nginx 需要 build）..."
	$(SAFE_BUILD_ENV) $(COMPOSE) $(PROD_INFRA_FILES) build nginx
	$(COMPOSE) $(PROD_INFRA_FILES) up -d --no-build nginx

infra-logs:
	$(COMPOSE) $(PROD_INFRA_FILES) logs -f postgres redis qdrant nginx certbot

infra-down:
	@echo "停止基础设施..."
	$(COMPOSE) $(PROD_INFRA_FILES) down --remove-orphans

infra-ps:
	$(COMPOSE) $(PROD_INFRA_FILES) ps

backend-up:
	@echo "启动后端服务..."
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d --no-build

backend-build:
	@echo "重构后端镜像..."
	$(COMPOSE) $(PROD_BACKEND_FILES) build ai-runtime platform
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d ai-runtime platform

backend-build-safe: ai-runtime-build-safe platform-build-safe
	@echo "后端镜像已按低 I/O 模式顺序重构并启动"

backend-logs:
	$(COMPOSE) $(PROD_BACKEND_FILES) logs -f ai-runtime platform

backend-down:
	@echo "停止后端服务..."
	$(COMPOSE) $(PROD_BACKEND_FILES) down --remove-orphans

backend-ps:
	$(COMPOSE) $(PROD_BACKEND_FILES) ps

frontend-up:
	@echo "校验当前前端静态发布..."
	@test -f $(FRONTEND_RELEASE_ROOT)/current/index.html || (echo "缺少已发布的前端静态资源，请先执行 make frontend-build" && exit 1)
	$(COMPOSE) $(PROD_INFRA_FILES) up -d --no-build nginx

frontend-build:
	@echo "构建并发布前端静态资源..."
	./scripts/publish-frontend.sh
	$(COMPOSE) $(PROD_INFRA_FILES) up -d --no-build nginx

frontend-build-safe:
	@echo "低 I/O 模式构建并发布前端静态资源..."
	$(SAFE_BUILD_ENV) ./scripts/publish-frontend.sh
	$(COMPOSE) $(PROD_INFRA_FILES) up -d --no-build nginx

frontend-logs:
	@echo "前端静态资源由共享 nginx 托管，以下为 nginx 日志:"
	$(COMPOSE) $(PROD_INFRA_FILES) logs -f nginx

frontend-down:
	@echo "前端静态资源已并入共享 nginx，无独立前端容器可停止"

frontend-ps:
	@echo "当前前端发布:"
	@readlink -f $(FRONTEND_RELEASE_ROOT)/current 2>/dev/null || echo "未找到 current 发布"

# ============================================
# 兼容的整栈命令
# ============================================

prod-check:
	@echo "检查 prod 启动前置条件..."
	@missing=""; \
	for image in $(PROD_REQUIRED_IMAGES); do \
		if ! docker image inspect "$$image" >/dev/null 2>&1; then \
			missing="$$missing $$image"; \
		fi; \
	done; \
	if [ -n "$$missing" ]; then \
		echo "缺少本地镜像，已阻止 make prod 触发隐式构建:$$missing"; \
		echo "请在资源充足的机器上显式执行 make infra-build/backend-build/frontend-build，或预先导入镜像。"; \
		exit 1; \
	fi
	@test -f $(FRONTEND_RELEASE_ROOT)/current/index.html || (echo "缺少已发布的前端静态资源，请先执行 make frontend-build"; exit 1)
	@if grep -Eq '^EMBEDDING_PROVIDER=local$$' ai_runtime/.env; then \
		if [ "$$ALLOW_LOCAL_EMBEDDING" != "1" ]; then \
			echo "检测到 ai_runtime/.env 使用 EMBEDDING_PROVIDER=local。"; \
			echo "首次启动会加载本地 sentence-transformers/torch，资源紧张机器上容易卡死。"; \
			echo "如需继续，请先改为 jina/openai，或使用 ALLOW_LOCAL_EMBEDDING=1 make prod 显式确认风险。"; \
			exit 1; \
		fi; \
	fi
	@echo "注意: 数据库现在由 Alembic 管理。首次部署先执行 make infra-up，再运行 make db-upgrade 或直接启动后端。"

prod: prod-check infra-up backend-up frontend-up
	@echo "生产环境已按 infra/backend/frontend 拆分方式启动"
	@echo "  - HTTP: http://localhost"
	@echo "  - 后端 API: http://localhost:8080"
	@echo "  - AI Runtime: http://localhost:8000"

prod-build: infra-build backend-build frontend-build
	@echo "生产环境镜像已按拆分方式重构并启动"

prod-build-safe: infra-build-safe ai-runtime-build-safe platform-build-safe frontend-build-safe
	@echo "生产环境镜像已按低 I/O 模式顺序重构并启动"

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

ai-runtime-build:
	@echo "仅重构 AI Runtime 镜像..."
	$(COMPOSE) $(PROD_BACKEND_FILES) build ai-runtime
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d --no-build ai-runtime

ai-runtime-up:
	@echo "仅启动 AI Runtime 服务..."
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d --no-build ai-runtime

ai-runtime-down:
	@echo "仅停止并移除 AI Runtime 服务容器..."
	-$(COMPOSE) $(PROD_BACKEND_FILES) stop ai-runtime
	-$(COMPOSE) $(PROD_BACKEND_FILES) rm -f ai-runtime

ai-runtime-build-safe:
	@echo "低 I/O 模式仅重构 AI Runtime 镜像..."
	$(SAFE_BUILD_ENV) $(COMPOSE) $(PROD_BACKEND_FILES) build ai-runtime
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d --no-build ai-runtime

api-up:
	@echo "仅启动 API 服务（platform）..."
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d --no-build platform

api-build:
	@echo "仅重构 API 镜像（platform）..."
	$(COMPOSE) $(PROD_BACKEND_FILES) build platform
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d --no-build platform

api-down:
	@echo "仅停止并移除 API 服务容器（platform）..."
	-$(COMPOSE) $(PROD_BACKEND_FILES) stop platform
	-$(COMPOSE) $(PROD_BACKEND_FILES) rm -f platform

api-build-safe:
	@echo "低 I/O 模式仅重构 API 镜像（platform）..."
	$(SAFE_BUILD_ENV) $(COMPOSE) $(PROD_BACKEND_FILES) build platform
	$(COMPOSE) $(PROD_BACKEND_FILES) up -d --no-build platform

platform-up: api-up

platform-build: api-build

platform-down: api-down

platform-build-safe: api-build-safe

ps:
	docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" --filter name=ai-platform

clean:
	@echo "清理当前统一部署环境..."
	-$(COMPOSE) $(PROD_FRONTEND_FILES) down -v --remove-orphans
	-$(COMPOSE) $(PROD_BACKEND_FILES) down -v --remove-orphans
	-$(COMPOSE) $(PROD_INFRA_FILES) down -v --remove-orphans
	@echo "清理完成"

test:
	@echo "运行本地测试..."
	cd ai_runtime && pytest
	cd platform && go test ./...

# ============================================
# 数据库与缓存
# ============================================

db-upgrade:
	@echo "执行 Alembic 升级..."
	docker compose $(PROD_BACKEND_FILES) run --rm --entrypoint alembic ai-runtime -c /app/db/alembic.ini upgrade head

db-current:
	@echo "查看当前 Alembic 版本..."
	docker compose $(PROD_BACKEND_FILES) run --rm --entrypoint alembic ai-runtime -c /app/db/alembic.ini current

db-history:
	@echo "查看 Alembic 历史..."
	docker compose $(PROD_BACKEND_FILES) run --rm --entrypoint alembic ai-runtime -c /app/db/alembic.ini history

db-revision:
	@test -n "$(m)" || (echo "用法: make db-revision m=add_some_change" && exit 1)
	@echo "创建 Alembic revision: $(m)"
	docker compose $(PROD_BACKEND_FILES) run --rm --entrypoint alembic ai-runtime -c /app/db/alembic.ini revision -m "$(m)"

db-reset-to-alembic:
	@echo "备份现有数据并重建为 Alembic 管理..."
	./scripts/db/reset_to_alembic.sh
	@echo "如已恢复历史知识库数据，请继续执行 make qdrant-backfill 重建 Qdrant 索引"

db-shell:
	@echo "连接到 PostgreSQL..."
	$(COMPOSE) $(PROD_INFRA_FILES) exec postgres psql -U ai_platform -d ai_platform

redis-cli:
	@echo "连接到 Redis..."
	$(COMPOSE) $(PROD_INFRA_FILES) exec redis redis-cli

qdrant-backfill:
	@echo "执行 Qdrant 全量回填..."
	$(COMPOSE) $(PROD_BACKEND_FILES) exec ai-runtime python /app/scripts/backfill_qdrant.py

# ============================================
# 服务重启
# ============================================

restart-platform:
	$(COMPOSE) $(PROD_BACKEND_FILES) restart platform

restart-ai-runtime:
	$(COMPOSE) $(PROD_BACKEND_FILES) restart ai-runtime

restart-frontend:
	@echo "前端已并入共享 nginx，无独立前端容器可重启；重新发布请执行 make frontend-build"

restart-nginx:
	$(COMPOSE) $(PROD_INFRA_FILES) restart nginx
