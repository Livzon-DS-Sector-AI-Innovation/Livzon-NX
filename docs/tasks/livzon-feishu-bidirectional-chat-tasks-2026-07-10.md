# Livzon 飞书双向对话任务账本

> 对应计划：`docs/livzon-feishu-bidirectional-chat-plan-2026-07-10.md`
>
> 状态定义：待处理 / 进行中 / 已完成 / 阻塞 / 已验证

## 当前状态

| 阶段 | 状态 | 当前结果 |
| --- | --- | --- |
| 需求与现状梳理 | 已完成 | 已确认现有 Livzon 应用只具备消息发送与卡片回调；全局飞书消息处理器仅去重/记录，未接入 Agent。 |
| 方案与接口决策 | 已完成 | 已确定私聊文本、持续会话、`/new`、完整回复、未授权提示和飞书确认卡片策略。 |
| 计划与进度文档 | 已完成 | 已将计划扩展为可交接实施的详细 Spec，并创建本任务账本。 |
| 后端统一事件长连接 | 已验证 | 已统一处理私聊消息与卡片动作，兼容旧开关并提供状态/重启 API。 |
| Agent 飞书公共入口与会话复用 | 已验证 | 已复用 JSONB 渠道会话、范围校验、`/new` 重置及既有 Agent 对话边界。 |
| 飞书确认卡片执行/取消 | 已验证 | 已校验原收件人、确认归属和到期时间；投递失败的动作会失效。 |
| 设置页、OpenAPI 与前端类型 | 已验证 | 已展示事件状态、错误、计数与重启操作，OpenAPI 和前端生成类型已同步。 |
| 自动化测试与验证 | 已验证 | 后端专项 32 项通过；Ruff、OpenAPI、生成类型、前端类型检查通过。 |
| 真实飞书卡片回传与收件人保护 | 进行中 | 代码、测试和后端重启已完成；仍待在飞书开放平台订阅并发布 `card.action.trigger` 后进行真实点击验收。 |
| 飞书私聊 Markdown 富文本回发 | 已验证 | Agent 完整答复现以交互卡片 Markdown 组件回发，粗体、列表与分隔线均有专项测试；后端已重启并健康检查通过。 |

## 已完成记录

### 2026-07-10：需求、架构与风险梳理

- 已定位现状：`identity.feishu_configs` 保存 Livzon 专属自建应用凭证；现有 `feishu_card_ws.py` 仅分发 `card.action.trigger`。
- 已定位现状：平台级 `im.message.receive_v1` 处理器只做 Redis 去重和日志记录，不会进入 Livzon Agent。
- 已确认复用边界：身份模块负责飞书身份、长连接和回发；Agent 模块应通过 `public_api` 负责权限检查、会话与确认执行。
- 已确认不需要数据库迁移，优先复用现有 Agent 会话上下文与飞书卡片动作记录。

### 2026-07-10：详细 Spec 固化

- 已将 `docs/livzon-feishu-bidirectional-chat-plan-2026-07-10.md` 扩展为详细 Spec。
- Spec 已明确事件协议、身份与权限规则、飞书渠道会话 JSONB 契约、`agent.public_api` 协作接口、确认卡片动作、状态 API、前端设置页、部署配置、测试矩阵和非功能安全要求。
- 源码尚未修改；下一阶段应先将“后端统一事件长连接”置为进行中再开始实现。

### 2026-07-13：开始后端事件连接实现

- 状态：进行中。
- 范围：`app/platform/identity`、`app/core/config.py`、`app/main.py` 与专项测试。
- 下一步：实现 `im.message.receive_v1` 事件分发、开关兼容和状态统计，再接入 Agent 公共入口。

### 2026-07-13：实现基线复核

- 已发现当前代码基线已包含统一事件长连接、`im.message.receive_v1` 分发、`LIVZON_FEISHU_EVENT_WS_ENABLED` 兼容开关、事件状态 API、Agent 渠道 public API、JSONB 会话复用及确认卡片分发。
- 当前缺口：未找到专项自动化测试，前端设置页尚未消费事件状态 API；还需补强确认卡片期限、投递异常不回滚 Agent 会话和审计验证。
- 状态：后端统一连接、Agent 渠道入口与确认卡片均保持进行中，待实现补强和测试通过后再完成。

### 2026-07-13：首轮后端编译与测试

- `uv run python -m compileall app/platform/identity/service.py app/platform/identity/feishu_card_ws.py app/modules/agent/public_api.py app/modules/agent/repository.py`：通过。
- `uv run pytest tests/unit/test_identity_feishu_messages.py -q`：被测试数据库安全保护阻止。当前数据库名为 `dazah` 而非专用测试库，未设置 `PYTEST_ALLOW_UNSAFE_DATABASE_URL`，未发生数据库写入。
- 后续：查找安全的 `TEST_DATABASE_URL` 配置；不得绕过该保护运行测试。

### 2026-07-13：功能补强与验证完成

- 后端事件处理：所有符合私聊入口条件的飞书消息在回复前按 `message_id` 去重；非文本消息也会去重后仅发送输入引导。事件状态统计采用 `im_message` 计数。
- 可靠性：飞书文本回发异常只记录脱敏日志，不回滚已经完成的 Agent 会话；确认卡片动作期限继承 `AgentConfirmation.expires_at`；确认卡片投递失败时对应动作标记为 `failed`，不会留下可执行的孤立动作。
- 审计：成功、拒绝和失败的 Agent 飞书入口只记录消息 ID、结果和会话/用户关联，不记录用户消息正文或飞书密钥。
- 前端：飞书设置页新增双向对话配置说明、事件连接状态、最近错误、事件计数、刷新与重启操作；使用 OpenAPI 生成的 `LivzonFeishuEventWsStatus` 类型。
- 测试：以从开发数据库连接安全派生的专用 `dazah_test` URL 运行专项测试，未使用 `PYTEST_ALLOW_UNSAFE_DATABASE_URL`；结果为 `32 passed`。覆盖私聊消息、非文本去重、渠道会话复用、`/new`、确认卡片期限、投递失败、确认执行及事件状态。
- 检查：后端 `ruff check` 通过；`compileall` 通过；OpenAPI 已以 `PYTHONIOENCODING=utf-8` 导出；`pnpm generate:api` 与 `pnpm typecheck` 通过。前端目标 ESLint 无错误，保留组件原有的 `react-hooks/set-state-in-effect` 警告。

### 2026-07-13：运行时消息未回复修复

- 现象：Livzon 专属长连接已成功连接，但机器人私聊没有回复；Redis 中不存在 `livzon:feishu:message:*` 入站去重键。
- 根因：运行日志显示消息由平台全局飞书 SDK 长连接接收后仅记录日志。只读比对确认 `FEISHU_APP_ID` 与 `identity.feishu_configs` 中的 Livzon App ID 相同，两个长连接竞争同一自建应用的事件投递。
- 修复：全局 `event_handler` 在检测到共享 App ID 时，将 `im.message.receive_v1` 的发送者、会话类型、消息 ID 和内容安全转交至 `handle_livzon_feishu_message_receive_event`；保留全局去重和 Livzon 去重，确保双重投递不会重复调用 Agent。
- 验证：新增共享应用转交及去重测试；专项回归 `32 passed`，Ruff 通过。已重启 `dazah-backend-app-1`，日志确认 Livzon 事件长连接重新建立。
- 下一步：在真实飞书机器人中再次发送一条私聊文本；日志应出现“共享飞书应用消息已转交 Livzon”，随后收到机器人回复。

### 2026-07-13：开始处理真实飞书卡片回传与收件人错误

- 状态：进行中。
- 现象：点击 Livzon 确认卡片后，飞书提示“目标回调服务当前未在线”；另一条执行提示为“无法解析飞书消息收件人”。
- 已确认根因一：全局飞书 SDK 长连接与 Livzon 原生长连接使用同一个 App ID。飞书长连接为集群随机投递；全局 SDK 未注册 `card.action.trigger`，卡片回传若落到该连接会失败。
- 已确认根因二：最新待确认项 `c46ddf04-4174-4670-bf70-05790f45ff1d` 的受控参数仅含收件人占位符 `user`，不属于本地已同步人员的可解析标识。未读取或记录消息正文、飞书凭证。
- 改动范围（待实施）：`app/platform/integrations/feishu/event_handler.py`、`app/platform/identity/agent_tools.py`、对应单元测试、前端飞书设置提示和本 Spec 的飞书回调配置说明。
- 验证计划：覆盖共享应用卡片动作转交、超时回执与无效收件人前置拒绝；随后重启后端并复测实际机器人卡片。

### 2026-07-13：共享 App 卡片回传与收件人保护实现完成

- 状态：代码已完成并已验证；真实飞书端点击验收仍进行中。
- 卡片回传修复：平台级 SDK 事件处理器新增 `card.action.trigger` 注册。当 `FEISHU_APP_ID` 与 Livzon App ID 相同时，随机落到全局连接的卡片动作会经身份模块的 `handle_livzon_feishu_card_action_event` 处理、在 2.5 秒内返回飞书 Toast，并记录脱敏事件 ID 与处理状态。
- 收件人修复：`identity.send_feishu_message` 等消息工具在创建确认项前拒绝 `user`、`当前用户`、`收件人` 等占位词；工具说明要求先查询已同步人员，再提交明确 UUID、飞书 ID、工号、手机号、邮箱或唯一姓名。最新错误确认项的 `user_ids=["user"]` 因而不会再进入可确认状态。
- 设置和 Spec：设置页及实施 Spec 明确区分“事件配置”的 `im.message.receive_v1` 与“回调配置”的新版 `card.action.trigger`，两者都必须使用长连接并在变更后发布应用；共享 App 由平台长连接统一注册并处理两个事件，避免为同一 App 重复建连。
- 验证命令/结果：
  - `uv run ruff check app\\platform\\integrations\\feishu\\event_handler.py app\\platform\\identity\\agent_tools.py tests\\unit\\test_feishu_event_handler.py tests\\unit\\test_identity_livzon_feishu_recipients.py`：通过。
  - `TEST_DATABASE_URL=<由 .env 的 DATABASE_URL 安全派生为 dazah_test> uv run pytest tests\\unit\\test_feishu_event_handler.py tests\\unit\\test_identity_livzon_feishu_events.py tests\\unit\\test_identity_feishu_messages.py tests\\modules\\agent\\test_feishu_public_api.py tests\\unit\\test_identity_livzon_feishu_recipients.py -q`：`35 passed`；仅有 39 条项目既有弃用警告。
  - `uv run python -m compileall app\\platform\\integrations\\feishu\\event_handler.py app\\platform\\identity\\agent_tools.py`：通过。
  - `pnpm typecheck`：通过；目标 ESLint 无错误，保留既有 `FeishuSettingsClient.tsx:132` 的 `react-hooks/set-state-in-effect` 警告。
  - `git diff --check`（前后端）：通过。
- 部署：已执行 `docker compose restart app`；容器运行正常，日志确认“Livzon 助手飞书事件长连接已连接”。
- 后续动作：在飞书开放平台为同一自建应用的“回调配置”选择长连接、订阅并发布 `card.action.trigger`；随后新建一张指定真实收件人的确认卡片并点击“确认执行”。

### 2026-07-16：确认卡片回调超时二次修复

- 现象：新版 `card.action.trigger` 已发布，后端也在 2.5 秒内完成动作并返回成功，但飞书客户端仍提示“目标回调服务超时未响应”。
- 根因：`identity.feishu_configs` 与平台 `FEISHU_APP_ID` 使用同一个 App ID，同时启动了平台 SDK 长连接和 Livzon 原生长连接；同一卡片动作被重复接收、重复回包。
- 修复：Livzon 事件连接启动时检测共享 App；若平台长连接已启用则直接复用，不再创建第二条回调连接。保留平台处理器对 `im.message.receive_v1` 和 `card.action.trigger` 的统一处理。
- 验证：目标单元测试 `7 passed`，Ruff 通过；容器重启后日志确认“复用平台长连接，不再启动重复回调连接”，健康检查 200，事件状态为运行中且无错误。
- 后续动作：生成一张新的确认卡片，完成无超时真实点击复测；旧卡片已执行或过期，不重复使用。

### 2026-07-16：确认卡片回调改为立即应答

- 复测证据：业务动作持续成功，但飞书约每 10 秒使用新事件 ID 重投同一次卡片动作，证明客户端没有接受到时 ACK；共享长连接同时处理耗时的私聊事件，回调排队时间不包含在原先 handler 内部的 2.5 秒等待上限中。
- 修复：SDK 同步回调不再等待数据库或下游网络调用，收到动作后立即返回“操作已受理，正在处理”；权限校验、幂等、执行和审计在主事件循环后台完成。
- 卡片闭环：后台事务提交后，使用飞书消息更新 API 主动替换原确认卡片为最终状态卡，避免保留可重复点击按钮。
- 验证：相关回归 `40 passed`，立即应答专项测试确认后台协程被人为阻塞时同步回调仍先返回；Ruff 与编译检查通过。
- 后续动作：部署后新建确认卡片，验证无超时提示、原卡片更新及下游操作结果。

### 2026-07-16：消除共享 SDK 接收线程的偶发阻塞

- 复测现象：确认动作能够执行且原卡片变绿，但在私聊 Agent 正在生成回复时点击确认卡片或下游“开始处理”仍偶发超时。
- 运行证据：一次私聊事件从接收到完成耗时约 16.7 秒；旧 `_on_message_receive` 在 SDK 接收线程中同步等待整个 Agent 任务，期间卡片帧尚未进入立即 ACK handler，因而仍会越过飞书 3 秒窗口。
- 修复：私聊 SDK handler 与卡片 handler 统一只负责调度后台协程并立即返回，SDK 接收线程不再等待 Agent、数据库或第三方网络调用。
- 下游闭环：`start_processing`、`mark_done` 等通用动作现在也返回原消息 ID 与绿色最终状态卡；事务提交后主动更新原飞书卡片，不再只写数据库状态、保留旧按钮。
- 验证：目标回归 `29 passed`，新增测试用阻塞协程证明消息 handler 会先返回；Ruff、编译和部署后健康检查通过。
- 后续动作：在 Agent 正在回复期间点击一张新确认卡片，并继续点击下游动作，验证两级卡片均无超时且会更新最终状态。

### 2026-07-16：收束高风险人工责任判断范围

- 现象：普通飞书交互卡片发送请求包含“确认执行”或“通过飞书发送”时，被聊天入口关键词策略误判为审批类高风险操作，未进入 `identity.send_feishu_message` 的正常确认流程。
- 根因：预判策略把“确认执行”列为高风险固定短语，并把单独的“通过”“同意”当作责任判断动作，覆盖范围大于工具注册表的实际风险元数据。
- 修复：高风险聊天预判仅保留审批、批准、驳回、拒绝和关键连接重启，并要求同时存在代执行语义；普通消息发送、创建/修改等可确认写操作及“确认执行”表述继续进入工具网关，由 confirmation 保护。
- 权威边界：`identity.send_feishu_message` 仍为 `write=true`、`risk_level=medium`、`human_decision_required=false`；真正的责任判断工具继续由注册表和执行器拒绝。
- 验证：后端策略及工具回归 `49 passed`，Hermes-Lite 提示词与工具测试 `6 passed`；运行态检查确认飞书确认发送不触发高风险拒绝，而审批通过与关键连接重启仍触发；后端和 Hermes-Lite 健康检查均通过。

### 2026-07-13：开始优化飞书私聊 Markdown 富文本回发

- 状态：进行中。
- 现象：机器人答复通过 `msg_type=text` 回发，飞书聊天文本不会渲染 Markdown，导致 `**粗体**` 与 `---` 原样显示。
- 实施范围：`app/platform/integrations/feishu/im.py` 的通用卡片构造、`app/platform/identity/service.py` 的私聊 Agent 回发分支，以及相关单元测试；系统提示和异常提示仍保持短文本消息。
- 设计：仅将 Agent 的完整答复封装为 `msg_type=interactive`、卡片 `markdown` 组件；发送前把独立分隔线规范为飞书支持的 `\\n ---\\n` 格式，保留粗体、标题、列表、链接等 Markdown 语义，不保存正文到日志或审计。
- 验证计划：覆盖消息类型、卡片 JSON、粗体/列表/分隔线规范化、飞书发送失败回退语义和原有私聊流程回归。

### 2026-07-13：飞书私聊 Markdown 富文本回发完成

- 状态：已验证。
- 实现：新增通用 `build_markdown_card_content` 和 `normalize_feishu_card_markdown`。完整 Agent 答复改用 `msg_type=interactive` 回发，卡片正文使用飞书 `markdown` 组件；独立 `---`、`***`、`___` 分隔线规范为 `\\n ---\\n`，粗体、列表、标题和链接保持原样交给飞书渲染。
- 兼容性：非文本消息、空输入、超长输入、权限提示及异常提示继续使用短文本；业务通知与确认卡片既有发送行为不变。日志与审计仍不记录答复正文。
- 文档：详细 Spec 的“飞书回复与确认卡片”已更新为 Markdown 富文本契约，并注明普通文本提示的保留范围。
- 验证命令/结果：
  - `uv run ruff check app\\platform\\integrations\\feishu\\im.py app\\platform\\integrations\\feishu\\__init__.py app\\platform\\identity\\service.py tests\\unit\\test_identity_feishu_messages.py tests\\unit\\test_identity_livzon_feishu_events.py`：通过。
  - `TEST_DATABASE_URL=<由 .env 的 DATABASE_URL 安全派生为 dazah_test> uv run pytest tests\\unit\\test_identity_feishu_messages.py tests\\unit\\test_identity_livzon_feishu_events.py tests\\unit\\test_feishu_event_handler.py tests\\modules\\agent\\test_feishu_public_api.py -q`：`35 passed`；仅有 39 条项目既有弃用警告。
  - `uv run python -m compileall app\\platform\\integrations\\feishu\\im.py app\\platform\\identity\\service.py`：通过。
  - `git diff --check`：通过。
- 部署：已执行 `docker compose restart app`；`GET http://127.0.0.1:8000/health` 返回 `200`，日志确认 Livzon 飞书事件长连接已连接。
- 后续动作：在飞书机器人私聊发送一条带粗体、列表和分隔线的问答，确认客户端呈现为卡片富文本，而非原始 Markdown 符号。

## 外部验收前提

代码任务已完成。部署管理员仍需在飞书开放平台为 Livzon 专属自建应用：

1. 开启机器人能力，并将应用发布到目标用户可用范围。
2. 订阅 `im.message.receive_v1`，选择长连接接收事件。
3. 在“回调配置”中选择长连接，订阅新版 `card.action.trigger`，然后创建并发布应用新版本；不要使用旧版 `card.action.trigger_v1`。
   同时删除机器人能力页面遗留的历史“消息卡片请求地址”，避免同一次点击并发触发新版长连接与已失效的旧 HTTP 回调。
4. 授予 `im:message.p2p_msg`（或只读版本）以及发送消息权限。
5. 设置 `LIVZON_FEISHU_EVENT_WS_ENABLED=true`（旧 `LIVZON_FEISHU_CARD_CALLBACK_WS_ENABLED=true` 亦兼容），重启后端并在设置页确认连接状态。
6. 重新同步通讯录后，用已授权用户完成私聊、`/new` 与确认卡片的真实飞书端到端验收。确认卡片的收件人必须是已同步人员的明确标识，不能是 `user` 等占位词。

## 未完成工作

- 飞书开放平台尚需在“回调配置”中订阅新版 `card.action.trigger`、选择长连接并发布应用；当前仅确认已开启 `im.message.receive_v1` 还不足以使确认卡片按钮可用。
- 完成配置后，需用一张新生成、且收件人为已同步人员明确标识的确认卡片，完成“确认执行 / 取消 / 重复点击”真实租户验收。前提和步骤见“外部验收前提”。

## 更新规则

- 每次开始源码改动前，将对应任务更新为“进行中”。
- 每次完成实现、运行测试、发现阻塞或完成验收后，追加日期、改动范围、命令结果和下一步。
