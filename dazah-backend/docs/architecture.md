# dazah-backend 项目架构

本项目采用模块化单体架构。模块清单和 schema 注册以
`app/shared/module_registry.py` 为准；记录归属、平台与业务边界见
`../../docs/business-module-boundaries.md`，开发约束见 `../AGENTS.md`。

## 目录结构

```text
app/
├── main.py
├── api/
│   └── router.py                 # 全局 API 路由装配
├── core/                         # 技术基础设施
│   ├── config.py
│   ├── database.py
│   ├── redis.py
│   ├── events.py
│   ├── exceptions.py
│   └── response.py
├── shared/                       # 跨平台和业务模块共享的轻量契约
│   ├── base_model.py
│   ├── module_api.py
│   ├── module_registry.py
│   └── schemas.py
├── platform/                     # 工厂级平台能力
│   ├── audit/                    # 审计日志和操作追踪
│   ├── identity/                 # 本地轻量用户档案，后续接飞书 SSO
│   ├── integrations/             # 飞书、ERP、LIMS 等外部系统适配
│   └── system/                   # 系统元数据接口
└── modules/                      # 业务模块，按负责人边界维护
    ├── agent/                     # 后端 Agent 工具网关和确认链路
    ├── production/
    ├── product/
    ├── equipment/
    ├── safety/
    ├── environment/
    ├── energy/
    ├── warehouse/
    ├── procurement/
    ├── administration/
    ├── hr/
    ├── research/
    ├── registration/
    ├── regulatory_tracker/
    ├── dossier_writer/
    └── quality/
```

## 模块约定

业务模块按需要组织以下职责；复杂模块可以拆为同名目录，不要求每个模块都
保留同样的单文件布局：

- `api.py`：HTTP 路由和请求参数处理
- `schemas.py`：Pydantic 请求/响应模型
- `service.py`：业务流程编排
- `repository.py`：数据库查询与持久化
- `models.py`：本模块 SQLAlchemy ORM 模型

跨模块调用优先通过对方模块的 `public_api.py`，不要直接导入其内部
Service、Repository 或 Model。外部系统的通用客户端和协议解析在
`platform/integrations/`；凭证、同步规则与状态处理在所属业务模块。

## 数据库边界

- `identity` schema：用户、可信身份和权限数据。
- `audit` schema：操作审计；实际保留策略以当前配置及迁移为准。
- 业务 schema 以模块注册表和当前 migration 为准，例如 `production`、
  `quality`、`equipment`。

## 接口入口

- `GET /health`
- `GET /api/v1/system/modules`
- 各模块路由由 `app/api/router.py` 装配；具体端点和 Schema 以生成的
  `openapi.json` 为准，不在本文件复制接口清单。
