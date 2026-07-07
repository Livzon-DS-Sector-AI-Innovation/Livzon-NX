# 质量模块业务迁移记录

日期：2026-07-06

## 背景

本次迁移将 `E:\飞书\Download\质量管理交接\质量管理交接` 作为质量模块增量交接包接入当前项目。迁移遵循当前项目规范：

- `dazah-backend/AGENTS.md`
- `dazah-frontend/AGENTS.md`
- `dazah-frontend/DESIGN.md`

迁移原则是以当前项目架构为准，交接包仅作为业务实现来源，不整包复制、不覆盖现有质量模块能力，尤其保留现有 CPV 能力。

## 迁移范围

已迁入能力：

- 偏差台账、报告记录、调查推送、AI 会话与附件分析
- CAPA 台账、CAPA 计划跟踪、CAPA 导入导出
- 变更台账、变更行动计划、飞书提醒/确认
- 验证主计划与设备确认、工艺验证、清洁验证、其他验证
- 质量飞书应用设置、实体绑定、字段映射、同步冲突查询
- 偏差、CAPA、变更台账 Word 导入/导出
- 后端 OpenAPI 与前端生成类型同步

未迁移内容：

- `__pycache__`
- `.pyc`
- `.orig`
- 交接包旧迁移编号文件
- 根目录临时脚本、调试脚本和脱离模块边界的产物

## 后端落点

后端业务代码统一落在：

```text
dazah-backend/app/modules/quality
```

主要新增或合并目录：

- `api/`
- `models/`
- `schemas/`
- `repository/`
- `service/`
- `templates/`

涉及少量平台/核心补充：

- `app/platform/integrations/feishu/auth.py`
- `app/platform/integrations/feishu/client.py`
- `app/platform/integrations/feishu/bitable.py`
- `app/core/config.py`

这些改动用于支持质量模块显式传入飞书凭证、Bitable 字段列表读取、质量模块环境兜底字段声明，未把质量飞书配置提升为平台全局配置来源。

## 路由合并

`app/modules/quality/api/__init__.py` 已合并并挂载：

- 现有 CPV 路由
- 质量管理主路由
- 验证路由
- 飞书 CAPA 路由

迁移后 CPV 能力仍保留，质量模块主路径仍挂载在 `/api/v1/quality`。

## 数据模型与迁移

基于当前 Alembic head 新建质量模块增量迁移链，未复用交接包旧 `down_revision`。

新增迁移链：

```text
a7c100000001_quality_import_export_fields.py
a7c100000002_quality_change_controls.py
a7c100000003_quality_ai_logs.py
a7c100000004_quality_change_action_plans.py
a7c100000005_quality_change_action_plan_reminders.py
a7c100000006_quality_validation_records.py
a7c100000007_quality_validation_record_fields.py
a7c100000008_quality_validation_detail_fields.py
a7c100000009_quality_validation_execution_tables.py
a7c100000010_quality_tracking_tables.py
a7c100000011_quality_deviation_ai_sessions.py
a7c100000012_quality_feishu_sync_fields.py
a7c100000013_quality_feishu_sync_metadata_fields.py
a7c100000014_quality_department_contacts_person_rows.py
a7c100000015_quality_feishu_settings_tables.py
a7c100000016_quality_feishu_entity_app_token.py
a7c100000017_quality_feishu_field_mappings.py
a7c100000018_quality_feishu_field_mapping_backfill.py
```

迁移约束：

- 新增表均使用 `quality` schema
- 新建表迁移包含 `CREATE SCHEMA IF NOT EXISTS quality`
- 本次新增迁移未创建数据库外键
- 未修改历史迁移
- 未创建无关模块迁移
- `downgrade()` 中的 `drop_table` 仅用于回滚本次新增质量表

当前 Alembic head：

```text
a7c100000018
```

## 飞书集成

质量模块飞书配置仍由质量模块自己的设置表和质量模块环境兜底字段管理。

平台层只补充通用能力：

- `FeishuAuth.get_tenant_access_token(app_id, app_secret)` 支持显式凭证
- `FeishuClient` 支持显式 app 凭证
- `BitableClient` 支持显式凭证、`list_fields()`、`search_records(..., automatic_fields=True)`

质量模块调用平台 helper 时显式传入质量模块解析出的配置，不让平台层反向读取质量模块业务配置。

## LLM 调用

质量 AI 能力使用：

```python
app.core.llm.llm_client
```

迁移后质量模块未引入：

- `AIService`
- `get_ai_service()`
- 硬编码模型配置

## 后端服务层调整

服务层按项目规范处理 SQLAlchemy async：

- 清理质量模块内 `await db.refresh(...)`
- INSERT 后使用 `flush` 或直接返回可用对象
- UPDATE/DELETE 后需要序列化对象时重新查询
- 保留软删除语义

同时修复：

- 飞书字段映射下的推送字段过滤与搜索条件构造
- 调查推送回拉只计数不落库的问题，改为“已有本地偏差/记录则更新快照，无本地偏差则只计数”
- 报告记录静态路由在飞书未启用时本地偏差兜底
- CAPA 导出模板位置，从 `service/` 移至 `templates/`
- 迁移过程遗留的本地 `127.0.0.1:7777` 调试上报代码

## 前端落点

页面落点：

```text
dazah-frontend/src/app/(dashboard)/quality
```

组件落点：

```text
dazah-frontend/src/components/quality
```

API 与 Actions：

```text
dazah-frontend/src/lib/api/quality.ts
dazah-frontend/src/actions/quality.ts
```

状态：

```text
dazah-frontend/src/stores/quality.ts
```

类型：

```text
dazah-frontend/src/types/generated/schema.ts
dazah-frontend/src/types/quality.ts
```

## 前端规范调整

已处理：

- `page.tsx` 保持 Server Component
- 运行时取数页面设置 `export const dynamic = 'force-dynamic'`
- 页面只从 `@/components/quality` 导入质量组件
- 写操作、同步、删除、保存配置、导入确认、AI 应用等收口到 `src/actions/quality.ts`
- `src/lib/api/quality.ts` 保留 GET/list/detail/search/download 薄封装
- `src/components/quality/index.ts` 统一导出新增组件
- 修复明显临时产物与 `.orig` 引用
- 前端类型从 OpenAPI 生成文件同步更新

仍保留为客户端 GET 的场景：

- 附件审阅列表读取
- 文件下载类 GET

## OpenAPI 与类型同步

后端已重新导出：

```text
dazah-backend/openapi.json
```

前端已同步：

```text
dazah-frontend/openapi.json
dazah-frontend/src/types/generated/openapi.json
dazah-frontend/src/types/generated/schema.ts
```

生成方式：

```powershell
uv run python scripts/export_openapi.py
node node_modules/openapi-typescript/bin/cli.js src/types/generated/openapi.json -o src/types/generated/schema.ts
```

备注：本机 `npx` 不可用，因此使用本地 Node 直接执行 `openapi-typescript` CLI。

## 验证结果

后端质量模块测试：

```text
uv run pytest tests/modules/quality -q
110 passed, 41 warnings
```

后端编译：

```text
uv run python -m compileall app/modules/quality app/platform/integrations/feishu app/core/config.py
通过
```

Alembic head：

```text
uv run alembic heads
a7c100000018 (head)
```

Alembic upgrade：

```text
uv run alembic upgrade head
通过
```

OpenAPI 导出：

```text
uv run python scripts/export_openapi.py
通过
```

前端类型生成：

```text
openapi-typescript 生成通过
```

前端类型检查：

```text
tsc --noEmit
```

质量模块无新增类型错误。当前失败来自既有能源模块依赖缺失：

```text
src/components/energy/DistributionChart.tsx: Cannot find module '@ant-design/charts'
src/components/energy/TrendChart.tsx: Cannot find module '@ant-design/charts'
```

## 已知遗留问题

`uv run alembic check` 仍检测到项目既有 schema drift，范围覆盖：

- product schema 新表差异
- core agent 相关表差异
- warehouse 飞书表注释、索引、外键差异
- 历史 CPV 外键与字段类型差异
- 部分历史 baseline 外键差异

这些 drift 不属于本次质量模块增量迁移独有问题。本次新增的 `a7c...` 质量迁移已单独确认：

- 无 `ForeignKey`
- 无 `ForeignKeyConstraint`
- 无无关模块变更
- 无 upgrade 阶段无关 `DROP TABLE`

## 后续建议

1. 单独处理项目既有 Alembic drift，不建议混入质量模块迁移提交。
2. 为能源模块补齐 `@ant-design/charts` 依赖或替换图表实现后，再跑全量前端 typecheck。
3. 在联调环境手动走查：
   - 质量首页
   - 偏差台账/报告记录/调查推送/AI 工作台
   - CAPA 台账/计划跟踪/导入导出
   - 变更台账/行动计划
   - 验证页面
   - 飞书设置与字段映射
4. 联调时重点确认飞书凭证不明文返回前端，缺配置、同步失败、表不存在时页面返回可读错误。
