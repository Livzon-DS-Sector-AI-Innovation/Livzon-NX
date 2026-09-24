# Alembic 迁移基线说明

本文件保留“曾考虑压缩迁移链”的背景，但**不是当前可执行的开发或部署流程**。
Dazah 已有被执行和作为基线使用的 migration；不得为缩短迁移链删除、重写
历史 revision，也不得用 `stamp`、手工 SQL 修改 `alembic_version` 或清除
Compose 数据卷来跳过迁移。数据库、Git 和授权边界以根目录 `AGENTS.md`
及 `dazah-backend/AGENTS.md` 为准。

## 当前开发流程

1. 根据业务归属修改 Model，并新增 Alembic revision。可用 autogenerate
   辅助生成，但必须逐行审查 `upgrade()`、`downgrade()`、数据回填、schema
   创建以及是否出现其他模块变化或未预期 DROP。
2. 检查代码只有一个 head。出现多个 head、版本不在现有迁移链或大量 drift 时
   停止，先分析分叉原因，不自动 merge revision、rebase 或重置数据库。
3. 在独立测试库验证空库升级、相关升级/降级和受影响数据库测试。测试库使用
   根目录 `.env.local` 中专用 `TEST_DATABASE_URL`，不得回退到开发库。
4. 启动本地开发后端前，确认 `DATABASE_URL` 是本次授权的开发库，比较
   `current` 与唯一 `head`。落后时通过根目录 `compose.dev.yml` 的
   `migrate` 服务升级，成功后再启动或重建 `app` 并检查健康状态。

具体命令和执行目录见 `../examples/commands.md` 与 `development.md`。
若未来确实需要压缩迁移历史，必须另立包含现有环境清单、数据保留、回滚、
多人同步和隔离验证的专项方案，并在执行前取得相应授权。
