# Livzon 飞书原生 Gateway

## 运行链路

生产对话链路为：

`飞书机器人 → Hermes v2026.7.7.2 FeishuAdapter → Hermes Agent → lark_cli → 飞书 Open API`

Hermes 镜像构建时按 SHA-256 校验并解包上游
`NousResearch/hermes-agent@v2026.7.7.2`。Gateway worker 原样实例化上游
`plugins/platforms/feishu/adapter.py`，复用其 WebSocket、重连、群聊 @、
媒体、去重、按会话串行、处理中状态和卡片回调实现。Dazah 的 Livzon
事件连接默认保持关闭，不能与 Hermes 长期并行消费同一应用。

官方 `@larksuite/cli` 固定为 `1.0.76`。27 个官方 Skills 嵌入 CLI
二进制，可通过 `lark_cli(["skills", "list"])` 与
`lark_cli(["skills", "read", "<skill>"])` 读取。文件操作优先使用
快捷命令和类型化命令，未覆盖时才使用 `api`。

## 配置

平台与 Hermes 必须配置相同的 `HERMES_INTERNAL_TOKEN`。Hermes 还需要：

- `HERMES_FEISHU_CREDENTIAL_KEY`：Fernet 密钥，用于加密持久化 App Secret。
- `LARK_CLI_PATH=/usr/local/bin/lark-cli`
- `HERMES_FEISHU_TMPFS=/run/hermes-feishu`

平台需要：

- `HERMES_INTERNAL_URL=http://hermes-lite:8100`
- Gateway 启用状态、租户和凭证由 Dazah 管理后台版本化下发。

管理员保存 Livzon 飞书设置后，平台以 HMAC 签名把新版本凭证推送到
Hermes。Hermes 使用 stdin 初始化 CLI、执行 `doctor`，成功后原子切换
tmpfs 配置并热重启 Gateway；失败时保留旧版本。

本地首次从 Dazah 旧事件连接切换时，可运行：

```powershell
uv run python scripts/configure_local_feishu_cutover.py
```

该脚本生成但不输出 Hermes 凭证加密密钥和内部服务 Token。重建后端与
Hermes 容器后，需要在平台
“系统设置 → 飞书设置”重新保存一次现有凭证，使平台将凭证安全推送到
Hermes。确认 Hermes `/internal/feishu/status` 返回
`configured=true`、`gateway=connected` 后再进行飞书对话测试。

## 权限和确认

每条消息由 Gateway 向 Dazah 解析可信身份和助手准入。Dazah RBAC 只用于
Dazah 业务工具；飞书原生资源只服从飞书授权。群聊必须满足 Dazah 准入且
必须 @Livzon。

中风险和高风险操作先执行官方 `--dry-run`。中风险可点击
“允许 / 始终允许 / 拒绝”；高风险只显示“允许 / 拒绝”且不允许记忆授权。
用户也可发送 `允许 <确认ID>`、`始终允许 <确认ID>`、`拒绝 <确认ID>`、
`查看授权` 和 `撤销授权 <授权ID>`。审批、驳回、处分等责任人决策由固定
规则直接拒绝代理执行。

写操作执行前必须成功写入 Hermes 本地脱敏审计 outbox。审计与资源变更
通知异步投递平台；失败使用持久队列退避补投，不阻塞已完成的飞书操作。
