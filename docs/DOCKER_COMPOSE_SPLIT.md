# Docker Compose 拆分说明

更新时间：2026-03-09

## 目标

将容器编排拆成三层：

- `docker-compose.infra.yml`
  包含 `postgres`、`redis`、`elasticsearch`、`nginx`、`certbot`
- `docker-compose.backend.yml`
  包含 `ai-runtime`、`platform`
- `docker-compose.frontend.yml`
  仅包含 `frontend`

这样可以分别重构和更新基础设施、后端、前端镜像，而不需要整栈联动。

## 文件说明

- [docker-compose.infra.yml](/mnt/ai-platform/docker-compose.infra.yml)
  负责创建共享网络 `ai-platform_ai-platform`，并承载数据库、缓存、搜索、网关与证书服务。
- [docker-compose.backend.yml](/mnt/ai-platform/docker-compose.backend.yml)
  后端服务挂到共享网络，通过 `postgres`、`redis`、`elasticsearch`、`nginx` 的服务名互通。
- [docker-compose.frontend.yml](/mnt/ai-platform/docker-compose.frontend.yml)
  前端服务挂到共享网络，由 `nginx` 反代。

## 启动顺序

先启动基础设施：

```bash
docker compose -f docker-compose.infra.yml up -d
```

再启动后端：

```bash
docker compose -f docker-compose.backend.yml up -d
```

最后启动前端：

```bash
docker compose -f docker-compose.frontend.yml up -d
```

对应的 `make` 命令：

```bash
make infra-up
make backend-up
make frontend-up
```

## 单独更新

只更新后端：

```bash
docker compose -f docker-compose.backend.yml build ai-runtime platform
docker compose -f docker-compose.backend.yml up -d ai-runtime platform
```

只更新前端：

```bash
docker compose -f docker-compose.frontend.yml build frontend
docker compose -f docker-compose.frontend.yml up -d frontend
```

对应的 `make` 命令：

```bash
make backend-build
make frontend-build
make infra-build
```

只更新基础设施中的 Nginx：

```bash
docker compose -f docker-compose.infra.yml build nginx
docker compose -f docker-compose.infra.yml up -d nginx
```

## 独立运维

查看基础设施日志：

```bash
docker compose -f docker-compose.infra.yml logs -f postgres redis elasticsearch nginx
```

查看后端日志：

```bash
docker compose -f docker-compose.backend.yml logs -f ai-runtime platform
```

查看前端日志：

```bash
docker compose -f docker-compose.frontend.yml logs -f frontend
```

## 兼容说明

- 现有 [docker-compose.yml](/mnt/ai-platform/docker-compose.yml)、[docker-compose.dev.yml](/mnt/ai-platform/docker-compose.dev.yml)、[docker-compose.prod.yml](/mnt/ai-platform/docker-compose.prod.yml) 保留，用于现有整栈流程兼容。
- 新拆分文件用于“单独更新镜像”和“按层运维”场景。
- `backend` 和 `frontend` 依赖 `infra` 先创建共享网络；如果未先启动 `infra`，单独拉起会因为缺少外部网络失败。
