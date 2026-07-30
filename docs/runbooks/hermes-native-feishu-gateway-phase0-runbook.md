# Hermes 原生 Feishu Gateway Phase 0 运行手册

> 适用版本：Dazah 固定
> `NousResearch/hermes-agent@v2026.7.7.2`（Hermes `0.18.2`）
>
> 固定 commit：`9de9c25f620ff7f1ce0fd5457d596052d5159596`

## 1. 目标与边界

本手册用于验证、发布、切换和回滚 Dazah 的 Hermes 原生 Feishu Gateway。
Gateway 负责飞书 WebSocket、消息标准化、群聊 `@` 门禁、Reaction、原生回复、
卡片回调、媒体缓存和主动投递。业务身份、权限、风险、确认和业务写入仍由
Dazah 后端最终裁决。

同一个飞书 App 在任何时刻只能存在一个生产事件消费者。不得同时启用旧 Dazah
飞书 WebSocket 和 Hermes Gateway。

## 2. 发布前检查

1. 确认工作树只包含计划内变更。
2. 确认 `Hermes-Lite/upstream-hermes.json` 中 tag、version、tag object、
   commit 和 archive SHA-256 均完整。
3. 运行上游专项测试：

   ```powershell
   cd Hermes-Lite
   .\.venv\Scripts\python.exe -m pytest tests\test_pinned_hermes_upstream.py -q
   ```

4. 运行 Hermes-Lite 全量测试：

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```

5. 构建镜像：

   ```powershell
   docker build --tag hermes-lite:phase0 .
   ```

6. 若外部软件源暂时不可用，允许单独验证固定上游 stage，但不得据此把完整镜像
   构建标记为通过：

   ```powershell
   docker build --target hermes-upstream --tag hermes-upstream:phase0 .
   ```

## 3. 配置原则

- 所有密钥通过既有安全配置链提供，不写入命令历史、文档、镜像或日志。
- `HERMES_INTERNAL_TOKEN` 和 `HERMES_AGENT_TOKEN` 必须使用不同用途的受管值。
- `HERMES_FEISHU_CREDENTIAL_KEY` 必须是有效 Fernet key。
- 生产保持 `HERMES_FEISHU_GATEWAY_ENABLED=true`；回滚时通过受控配置改为
  `false`。
- `HERMES_UPSTREAM_DIR` 在生产保持 `/opt/hermes-upstream`。
- `/opt/hermes-upstream` 只读，运行用户不得修改。
- `/run/hermes-feishu` 使用 tmpfs，权限保持 `0700`。
- `HERMES_GATEWAY_LOCK_DIR` 保持
  `/run/hermes-feishu/gateway-locks`，使上游单消费者锁可在只读容器中工作。

不得在排障记录中复制 App Secret、Token、Cookie、签名或解密后的配置。

## 4. 启动与健康验证

启动后查询内部状态接口。请求必须携带内部 Bearer Token，示例中的占位符不能
替换进文档：

```text
GET /internal/feishu/status
Authorization: Bearer <internal-token>
```

通过标准：

- `configured=true`
- `gateway=connected`
- `gateway_upstream.release_tag=v2026.7.7.2`
- `gateway_upstream.release_version=0.18.2`
- `gateway_upstream.commit_sha=9de9c25f620ff7f1ce0fd5457d596052d5159596`
- `pending_deliveries` 没有持续增长
- `gateway_reconnects` 没有持续抖动

`starting` 表示 Adapter 尚未完成连接；`failed` 或 `inactive` 不得进入生产切换。

## 5. 测试应用验收

按顺序执行并保存脱敏证据：

1. 私聊发送可产生多段回复的普通文本，确认出现处理中 Reaction、同一条原生
   富文本消息被增量更新、最终内容收口，成功后 Reaction 被清理。
2. 白名单群中 `@Livzon`，确认收到引用/Thread 内回复。
3. 未 `@`、非白名单群、未授权用户分别确认 fail-closed。
4. 发送图片、文本文件、PDF、音频和视频，确认 Gateway 缓存且不存在越界路径
   读取。
5. 触发中风险写操作，确认卡片包含“允许 / 始终允许 / 拒绝”。
6. 触发高风险写操作，确认卡片只包含“允许 / 拒绝”。
7. 用原请求人点击一次，确认只执行一次并产生审计。
8. 用其他账号点击、重复点击、过期后点击，确认均不执行。
9. 创建主动文本和卡片投递，确认同一 idempotency key 只投递一次，状态最终为
   `delivered` 并记录 message_id。
10. 模拟一次可重试发送失败，确认状态经历 `retry`；连续三次失败后为 `failed`。

任何 mock 测试不得替代上述真实测试应用验收。

## 6. 主动投递

写入接口：

```text
POST /internal/feishu/deliveries
Authorization: Bearer <internal-token>
Content-Type: application/json
```

文本请求示意：

```json
{
  "idempotency_key": "<domain-event-id>:<recipient-id>",
  "chat_id": "<feishu-chat-id>",
  "content": "待投递内容",
  "metadata": {
    "source": "quality"
  }
}
```

调用方必须保存返回的 delivery id，并通过
`GET /internal/feishu/deliveries/{delivery_id}` 查询最终状态。`accepted` 或
HTTP 202 只表示已进入 outbox，不表示飞书已送达。

## 7. 生产切换

1. 冻结飞书配置变更。
2. 在测试 App 完成第 5 节全部验收。
3. 启动生产 Hermes，确认状态为 `connected` 且 provenance 完全匹配。
4. 停止旧 Dazah 飞书事件消费者。
5. 检查飞书开发者后台和运行实例，确认只有一个生产消费者。
6. 执行私聊、白名单群、确认卡片和主动投递最小冒烟。
7. 观察错误率、重连次数、outbox 深度和重复投递至少一个业务高峰窗口。
8. 记录切换时间、操作者、版本、commit、验证结果和回滚负责人。

## 8. 回滚

触发条件包括：Gateway 无法稳定连接、消息重复、确认可能重复执行、身份错误、
权限旁路、outbox 持续堆积或真实飞书体验核心路径失败。

回滚步骤：

1. 设置 `HERMES_FEISHU_GATEWAY_ENABLED=false` 并确认 Gateway 为 `inactive`。
2. 确认 Hermes WebSocket 已断开后再恢复旧消费者，禁止重叠。
3. 暂停主动投递生产者，保留 outbox 数据，不手工改为 delivered。
4. 对 `sending`、`retry` 和 `failed` 记录按 message_id 与业务事件逐条核对。
5. 恢复上一已验证镜像和配置版本。
6. 执行旧链路最小冒烟并记录回滚证据。
7. 在重新切换前完成根因修复和重复执行风险审计。

## 9. 凭证轮换

凭证更新必须使用递增 version。候选凭证先经过 lark-cli 初始化、
`config bind --source hermes --identity bot-only`、bot-only strict-mode 和
doctor 探测，全部成功后原子替换。绑定使用的临时 Hermes `.env` 只能位于
`/run/hermes-feishu` 私有 tmpfs，权限为 `0600`，完成后立即删除。探测失败时
保留旧版本，不得删除仍可工作的凭证。轮换后确认 Gateway 重连一次并重新报告
`connected`。

多维表格只读诊断依次执行：

```text
lark-cli base +url-resolve --url "<Base URL>" --as bot
lark-cli base +table-list --base-token "<base_token>" --as bot
lark-cli base +field-list --base-token "<base_token>" --table-id "<table_id>" --as bot
lark-cli base +record-list --base-token "<base_token>" --table-id "<table_id>" --limit 50 --format json --as bot
lark-cli base +record-search --base-token "<base_token>" --table-id "<table_id>" --keyword "<keyword>" --search-field "<field_name>" --limit 20 --format json --as bot
```

本部署固定为 bot-only；Agent 不得使用 `--as user`，也不得在 user 身份缺失后
把飞书原生资源错误降级成 Dazah 已登记业务数据源。

`subject` 是 Dazah AgentBackend V2 和 `dazah_tool` 的可信鉴权字段，不是飞书
Open API 或 `lark_cli` 参数。能列出数据表和字段、但读取具体记录失败时，先确认
Agent 实际调用的是 `base +record-list` 或 `base +record-search`，再根据 CLI 返回的
飞书错误码检查 `base:record:read` Scope、目标 Base 的文档应用授权和高级权限。
Gateway 向 AgentBackend V2 转发连续飞书对话时，`messages` 必须携带同一
`session_id` 最近最多 20 条用户/助手消息；不得固定为空，否则用户在下一轮只回复
数据表名称时会丢失 Base URL 和 table_id 上下文。该历史仅在 Gateway 进程内有界
缓存，不写日志，也不替代 Hermes 自身的会话存储。

Hermes 通过 Docker Compose 运行时，Dazah 后端地址必须使用同一 Docker 网络
中的服务名：

```text
DAZAH_API_BASE_URL=http://app:8000/api/v1
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
```

不得配置为 `127.0.0.1:8000` 或 `localhost:8000`；容器内的 loopback 指向
Hermes 自身，会导致 `ConnectError: All connection attempts failed`。

出现“隔一段时间又回复同一条旧消息”时，按以下顺序区分两类重复：

1. 检查同一用户消息是否产生多次 `/v2/agent/runs/stream`。若是，核对
   `inbound_message_receipts` 是否存在同一 `message_id` 的完成收据，并确认只有
   一个生产 Gateway 消费者。
2. 若只产生一次 Agent run，但飞书出现两个回复气泡，检查最终
   `edit_message` 是否失败。流式首气泡一旦成功创建，终态编辑失败只能重试编辑，
   不得再发送一条完整答案作为回退。
3. 固定上游 Adapter 的 JSON 去重保留 24 小时；Dazah Gateway 另以 SQLite
   原子收据保留 7 天，覆盖并发、子进程重启和多实例误重叠。处理中收据租约为
   1 小时，进程崩溃后允许恢复；已完成收据在保留期内不得再次执行。
4. 验收时对同一 `message_id` 并发投递两次，必须只产生一次 Agent run 和一个
   回复气泡；再模拟最终编辑连续失败，必须保留已有气泡且不得创建第二个气泡。

## 10. 验收记录

每次发布至少保存：

- 镜像标识和构建结果
- upstream tag/version/commit/archive SHA-256
- 本地全量测试结果
- 测试 App 十项验收结果
- 单消费者证明
- 生产冒烟结果
- outbox、重连和错误指标
- 回滚演练结果
- 未执行项、负责人和恢复条件
