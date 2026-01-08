# 📚 文档导航 | Documentation Guide

本项目的文档已整理完毕，采用"去芜存菁"的原则，只保留最核心和实用的文档。

The documentation has been streamlined following the principle of "keeping the essence" - only core and practical docs remain.

---

## 🌏 主要文档 | Main Documentation

### 中文版 (Chinese)
- **[README_CN.md](README_CN.md)** - 完整的中文项目文档
  - 项目介绍和架构
  - 快速开始指南（3种启动方式）
  - 功能特性详解（JWT、Chat API、数据库、RAG、Agent）
  - API 完整文档（认证端点、聊天端点）
  - 数据库配置指南
  - 开发和部署指南
  - 常见问题解答（FAQ）

### English
- **[README.md](README.md)** - Complete English project documentation
  - Project introduction and architecture
  - Quick start guide (3 startup methods)
  - Feature details (JWT, Chat API, Databases, RAG, Agent)
  - Complete API documentation (Auth & Chat endpoints)
  - Database configuration
  - Development and deployment guides
  - FAQ

---

## 📖 技术文档 | Technical Documentation

位于 `docs/` 目录 | Located in `docs/` directory:

### 认证系统 | Authentication
- **[docs/JWT_AUTHENTICATION.md](docs/JWT_AUTHENTICATION.md)** (English)
  - Complete JWT authentication guide
  - API endpoint specifications
  - Authentication flow
  - Token management
  - Security best practices

- **[docs/JWT_AUTHENTICATION_ZH.md](docs/JWT_AUTHENTICATION_ZH.md)** (中文)
  - JWT 认证完整指南
  - API 端点详细说明
  - 认证流程说明
  - Token 管理
  - 安全最佳实践

### 数据库 | Database
- **[docs/DATABASE_GUIDE.md](docs/DATABASE_GUIDE.md)** (English)
  - PostgreSQL configuration and usage
  - Redis cache implementation
  - Elasticsearch vector search
  - Database schema design
  - Connection configuration
  - Performance optimization
  - Monitoring and troubleshooting

- **[docs/DATABASE_GUIDE_ZH.md](docs/DATABASE_GUIDE_ZH.md)** (中文)
  - PostgreSQL 配置和使用
  - Redis 缓存实现
  - Elasticsearch 向量搜索
  - 数据库模式设计
  - 连接配置
  - 性能优化
  - 监控和故障排查

---

## 📝 示例和脚本 | Examples & Scripts

### API 示例 | API Examples
位于 `examples/` 目录 | Located in `examples/` directory:

- **auth_examples.sh / auth_examples.bat**
  - JWT 认证示例（Linux/Mac 和 Windows）
  - 注册、登录、刷新 token
  - 使用 token 访问 API

- **api_examples.sh**
  - 完整的 API 使用示例
  - 聊天接口调用
  - RAG 和 Agent 使用

- **websocket_client_jwt.html**
  - WebSocket 客户端示例
  - 带 JWT 认证的在线聊天
  - 在浏览器中打开即可使用

### 工具脚本 | Utility Scripts
位于 `scripts/` 目录 | Located in `scripts/` directory:

- **init-databases.sh / init-databases.bat**
  - 一键启动所有数据库
  - 健康检查和状态显示

- **generate_proto.sh / generate_proto.bat**
  - 生成 gRPC 代码
  - Python 和 Go stubs

---

## 🗂️ 文档结构 | Documentation Structure

```
ai-platform/
├── README.md                           # 英文主文档 | English main README
├── README_CN.md                        # 中文主文档 | Chinese main README
├── DOCS_GUIDE.md                       # 本文件 | This file
│
├── docs/                               # 核心技术文档 | Core technical docs
│   ├── JWT_AUTHENTICATION.md          # JWT 认证指南 (English)
│   ├── JWT_AUTHENTICATION_ZH.md       # JWT 认证指南 (中文)
│   ├── DATABASE_GUIDE.md              # 数据库指南 (English)
│   ├── DATABASE_GUIDE_ZH.md           # 数据库指南 (中文)
│   └── archive/                        # 历史文档存档
│       ├── JWT_AUTH_COMPLETE.md
│       ├── DATABASE_INTEGRATION_COMPLETE.md
│       ├── QUICKSTART_JWT.md
│       ├── PROJECT_README.md
│       └── PROJECT_OVERVIEW.md
│
├── examples/                           # 示例代码
│   ├── auth_examples.sh               # 认证示例（Linux/Mac）
│   ├── auth_examples.bat              # 认证示例（Windows）
│   ├── api_examples.sh                # API 示例
│   └── websocket_client_jwt.html      # WebSocket 客户端
│
└── scripts/                            # 工具脚本
    ├── init-databases.sh              # 数据库初始化（Linux/Mac）
    ├── init-databases.bat             # 数据库初始化（Windows）
    ├── generate_proto.sh              # gRPC 代码生成（Linux/Mac）
    └── generate_proto.bat             # gRPC 代码生成（Windows）
```

---

## 🎯 根据需求查找文档 | Find Docs by Need

### 我想...  | I want to...

#### 快速开始 | Quick Start
→ 阅读 **README_CN.md** 或 **README.md** 的"快速开始"章节
→ Read the "Quick Start" section in **README_CN.md** or **README.md**

#### 了解认证系统 | Learn about authentication
→ **docs/JWT_AUTHENTICATION.md** (English) - Complete authentication guide
→ **docs/JWT_AUTHENTICATION_ZH.md** (中文) - 完整认证指南

#### 配置数据库 | Setup databases
→ **docs/DATABASE_GUIDE.md** (English) - Complete database guide
→ **docs/DATABASE_GUIDE_ZH.md** (中文) - 完整数据库指南
→ 运行 `scripts/init-databases.sh` 一键启动

#### 查看 API 示例 | See API examples
→ **examples/auth_examples.sh** - 认证示例
→ **examples/api_examples.sh** - API 示例
→ **examples/websocket_client_jwt.html** - WebSocket 示例

#### 部署到生产环境 | Deploy to production
→ **README_CN.md** 或 **README.md** 的"部署指南"章节
→ "Deployment" section in **README_CN.md** or **README.md**

#### 二次开发 | Development
→ **README_CN.md** 或 **README.md** 的"开发指南"章节
→ "Development" section in **README_CN.md** or **README.md**

#### 问题排查 | Troubleshooting
→ **README_CN.md** 或 **README.md** 的"常见问题"章节
→ **docs/DATABASE_GUIDE.md** 的故障排查部分
→ "FAQ" section or "Troubleshooting" in guides

---

## ✅ 文档清单 | Documentation Checklist

## 💡 文档使用建议 | Documentation Tips

### 新用户 | New Users
1. 先读主 README（README.md 或 README_CN.md）
2. 按照快速开始指南启动项目（3种方式可选）
3. 查看 examples/ 目录的示例代码学习使用
4. 遇到问题查看 FAQ 部分

### 开发者 | Developers
1. 阅读主 README 的"开发指南"部分
2. 查看 docs/ 目录的详细技术文档
3. 参考 examples/ 目录的示例代码
4. 使用 scripts/ 目录的工具脚本

### 运维人员 | Operations
1. 阅读"部署指南"章节
2. 查看"数据库指南"配置生产环境
3. 参考"监控"和"故障排查"章节
4. 使用生产部署检查清单


## 🗄️ 归档文档说明 | Archived Documents

位于 `docs/archive/` 的文档已被整合到主文档中：

Docs in `docs/archive/` have been consolidated into main docs:

- **PROJECT_README.md** → 内容已整合到 README.md
- **PROJECT_OVERVIEW.md** → 内容已整合到 README.md
- **JWT_AUTH_COMPLETE.md** → 内容已整合到 README.md 和 JWT_AUTHENTICATION.md
- **DATABASE_INTEGRATION_COMPLETE.md** → 内容已整合到 README.md 和 DATABASE_GUIDE.md
- **QUICKSTART_JWT.md** → 内容已整合到 README.md 的快速开始部分

这些文件保留在 archive/ 目录供参考，但不再维护。

These files are kept in archive/ for reference but are no longer maintained.

---

## 🔄 文档更新 | Documentation Updates

文档最后更新：2025-12-20
Last updated: 2025-12-20

