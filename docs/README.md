# 技术文档目录 | Technical Documentation

本目录包含 AI Platform 的核心技术文档，所有文档均提供中英文双语版本。

This directory contains the core technical documentation for AI Platform. All documents are available in both Chinese and English.

---

## 📚 文档列表 | Documentation List

### 🔐 JWT 认证 | JWT Authentication

完整的 JWT 认证系统文档，包括 API 端点、认证流程、Token 管理和安全最佳实践。

Complete JWT authentication system documentation, including API endpoints, authentication flow, token management, and security best practices.

- **[JWT_AUTHENTICATION.md](JWT_AUTHENTICATION.md)** (English)
  - JWT authentication overview and architecture
  - Complete API endpoint specifications
  - Request/response examples
  - Token structure and claims
  - Security best practices
  - Error handling
  - Demo user credentials

- **[JWT_AUTHENTICATION_ZH.md](JWT_AUTHENTICATION_ZH.md)** (中文)
  - JWT 认证概述和架构
  - 完整的 API 端点规范
  - 请求/响应示例
  - Token 结构和声明
  - 安全最佳实践
  - 错误处理
  - 演示用户凭据

### 💾 数据库 | Database

三个数据库系统的完整配置和使用指南：PostgreSQL、Redis 和 Elasticsearch。

Complete configuration and usage guide for three database systems: PostgreSQL, Redis, and Elasticsearch.

- **[DATABASE_GUIDE.md](DATABASE_GUIDE.md)** (English)
  - Database architecture overview
  - PostgreSQL setup and schema design
  - Redis cache implementation
  - Elasticsearch vector search for RAG
  - Connection configuration
  - Performance optimization
  - Monitoring and troubleshooting
  - Backup and recovery

- **[DATABASE_GUIDE_ZH.md](DATABASE_GUIDE_ZH.md)** (中文)
  - 数据库架构概述
  - PostgreSQL 配置和模式设计
  - Redis 缓存实现
  - Elasticsearch 向量搜索（RAG）
  - 连接配置
  - 性能优化
  - 监控和故障排查
  - 备份和恢复

---

## 🎯 快速导航 | Quick Navigation

### 我想... | I want to...

#### 了解如何使用 JWT 认证 | Learn JWT authentication
→ 阅读 [JWT_AUTHENTICATION.md](JWT_AUTHENTICATION.md) 或 [JWT_AUTHENTICATION_ZH.md](JWT_AUTHENTICATION_ZH.md)

#### 配置数据库 | Setup databases
→ 阅读 [DATABASE_GUIDE.md](DATABASE_GUIDE.md) 或 [DATABASE_GUIDE_ZH.md](DATABASE_GUIDE_ZH.md)
→ 运行 `../scripts/init-databases.sh` 一键启动所有数据库

#### 查看 API 示例 | See API examples
→ 查看 [../examples/](../examples/) 目录
→ 运行 `../examples/auth_examples.sh` 测试认证 API

#### 了解项目整体架构 | Understand project architecture
→ 返回主文档 [../README.md](../README.md) 或 [../README_CN.md](../README_CN.md)

---

## 📖 文档特点 | Documentation Features

### ✅ 完整性 | Completeness
- 涵盖所有核心功能的详细文档
- 包含完整的代码示例和 API 规范
- 提供故障排查和最佳实践指南

### 🌏 双语支持 | Bilingual Support
- 所有技术文档都有中英文版本
- 保持两个版本内容同步更新
- 便于不同语言背景的开发者使用

### 🎨 结构清晰 | Clear Structure
- 统一的文档格式和风格
- 清晰的章节划分和目录
- 易于查找和导航

### 🔄 持续更新 | Continuous Updates
- 随项目功能更新而更新
- 标注最后更新日期
- 保持文档与代码同步

---

## 🗂️ 文档结构 | Documentation Structure

```
docs/
├── README.md                       # 本文件 | This file
│
├── JWT_AUTHENTICATION.md           # JWT 认证指南 (English)
├── JWT_AUTHENTICATION_ZH.md        # JWT 认证指南 (中文)
│
├── DATABASE_GUIDE.md               # 数据库指南 (English)
└── DATABASE_GUIDE_ZH.md            # 数据库指南 (中文)
```

---

## 📞 更多资源 | More Resources

### 主要文档 | Main Documentation
- **项目主页**: [../README.md](../README.md) (English) / [../README_CN.md](../README_CN.md) (中文)
- **文档导航**: [../DOCS_GUIDE.md](../DOCS_GUIDE.md) - 完整的文档导航指南

### 前端文档 | Frontend Documentation
- **Vue 3 前端**: [../frontend-vue/README.md](../frontend-vue/README.md) (English)
- **Vue 3 前端**: [../frontend-vue/README_CN.md](../frontend-vue/README_CN.md) (中文)

### 示例和脚本 | Examples & Scripts
- **API 示例**: [../examples/](../examples/) - 认证、聊天、WebSocket 示例
- **工具脚本**: [../scripts/](../scripts/) - 数据库初始化、gRPC 代码生成

### 数据库迁移 | Database Migrations
- **SQL 迁移文件**: [../db/migrations/](../db/migrations/) - 数据库模式定义

---

## 🔄 文档更新 | Documentation Updates

**最后更新 | Last Updated:** 2026-01-17

**更新内容 | Updates:**
- 整合和清理了所有技术文档
- 统一了中英文文档格式
- 添加了完整的文档导航
- 更新了 Docker 部署相关文档

---

## 💡 使用建议 | Usage Tips

### 新手开发者 | New Developers
1. 从主 README 开始了解项目整体架构
2. 阅读 JWT_AUTHENTICATION 文档了解认证系统
3. 阅读 DATABASE_GUIDE 文档了解数据库配置
4. 查看 examples/ 目录的示例代码
5. 使用 scripts/ 目录的工具脚本快速启动

### 经验开发者 | Experienced Developers
1. 直接查看相关技术文档的 API 规范部分
2. 参考代码示例快速集成
3. 查看故障排查部分解决问题
4. 参考最佳实践优化实现

### 运维人员 | Operations
1. 重点阅读数据库配置和监控部分
2. 查看备份和恢复指南
3. 了解性能优化建议
4. 参考故障排查流程

---

**如有问题或建议，请提交 Issue 或 Pull Request。**

**For questions or suggestions, please submit an Issue or Pull Request.**