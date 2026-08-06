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

## 原生文件能力

Livzon 助手可在飞书会话和 Dazah Web Agent 中读取并操作已由固定 CLI
支持的文件型资源：云文档、云盘文件和文件夹、电子表格、多维表格、Wiki、
幻灯片、原生 Markdown、思维笔记、妙记/笔记和画板。所有命令固定使用
`--as bot`；Web 登录身份不会转换成飞书用户身份，目标资源必须已经授权给
Livzon 飞书应用。

写入前必须读取对应的内置 Skill，并优先使用类型化 shortcut。普通修改、
创建和重命名属于中风险；删除、清空、覆盖、移动和批量操作属于高风险；
小范围追加或评论可直接执行。修改后必须只读回查，删除后必须验证目标不存在，
创建操作必须取得结构化资源回执。共享、成员、权限、所有权、Base 角色和高级
权限不属于本能力，审批、驳回、处分等责任判断仍直接拒绝。

只读回查会对飞书短暂一致性进行有限重试，并以覆盖写入内容首、中、尾的脱敏
锚点核验结构化返回。只有 CLI 写入成功且回查完全匹配时状态才是 `completed`；
回查失败统一记为 `verification_failed`、返回 `ok=false`，不得生成“始终允许”
授权、资源变更成功事件或“操作已执行”回复。

Gateway 同时检查 CLI 进程退出码和 JSON 语义字段（`ok`、`success`、`code`、
`status/state`）；退出码为 0 但语义为失败、取消、超时、过期、仍在排队/处理中，
或批量结果包含失败项、失败计数及成功数小于总数时，均不得视为执行成功。
模型提供的只读命令只能作为候选，网关必须确认资源域、父资源、子资源和范围标识
与写命令一致。普通 readback 必须包含可比较的字段值或文本锚点，不能再用“命令
成功返回”代替业务结果匹配；缺少可执行验证契约时不创建确认项，历史待确认项则
在执行前标记为 stale，禁止先写后报验证失败。

已选定 Base 数据表中的单行新增走受限快速路径：复用最近会话中的目标标识，
只允许按需各读取一次 Skill、字段和少量样例，最终统一使用
`base +record-upsert --json <顶层字段对象>`，并将工具轮次限制为 10。旧的
`record-create`、单元素批量写法和错放的内联 JSON 会在安全边界归一化；运行
超时或客户端断开会触发协作取消门，后续工具调用不得再创建确认项或产生写入。

Base 单行快速路径中的日期/时间必须使用 `YYYY-MM-DD HH:mm:ss` 字符串，禁止
模型计算 Unix 时间戳；日期还会与批次号等字段中的 `YYYYMMDD` 做一致性检查。
确认卡预览直接由最终 CLI JSON 生成。执行后从创建回执提取 `record_id`，调用
`base +record-get` 精确回读，并按日期、单选等 Base 规范化表示逐字段核对；只有
全部提交字段一致时才返回成功。
Base 单条删除同样不接受 `record-list` 等宽泛回读：Gateway 会从已执行的删除命令
提取 Base、数据表和记录 ID，强制调用 `base +record-get`，仅在 CLI 明确返回
`record_not_found` 时判定删除成功；记录仍可读取时继续保持验证失败。旧版本已执行
但误判为验证失败的单条删除可只重跑该精确回读并纠正状态，禁止重放删除命令。
Base 已有记录的单条 upsert 和批量 update 也由网关从写入 JSON 提取全部记录 ID，
使用一次精确 `record-get` 回读并逐记录、逐字段比较；批量删除必须确认全部目标 ID
都在 `record_not_found` 中，批量新增也必须回读全部新记录并逐字段比较，任何部分
成功都不能判定整批成功。

Sheets 单元格写入必须以同一 spreadsheet、sheet 和 A1 range 回读并匹配提交值；
工作表删除使用同一工作簿的完整 metadata 列表确认目标 sheet ID/名称消失。Drive、
Wiki 和 Base 子资源的精确删除使用对应 inspect/get 命令并识别 CLI JSON 中的语义
not-found。移动、重命名、Slides、Markdown、画板等写入只有在同一目标回读中能
匹配新位置、新名称或内容锚点时才允许执行；无法构造强后置条件的命令会在写入前
停止，不会降级为仅检查退出码。

非 Base 创建只允许白名单中的类型化创建命令使用 `creation_receipt`。网关从回执
提取该资源类型专属 ID，并自行构造 Docs fetch、Sheets workbook/object list、Drive
inspect、Wiki node-get、Slides xml-get 或 Markdown fetch；派生查询成功且创建内容
锚点匹配后才完成。Docs 块操作必须把 `--block-id` 绑定到 fetch 的
`--start-block-id`，Slides 必须绑定真实 `--presentation`/`--slide-id`；Sheets 图表、
条件格式、筛选视图、浮动图片、透视表和 sparkline 也必须绑定对象 ID。原生 API
回查必须携带写请求 `params` 中的全部 `*_id`/`*_token`，不能只匹配父资源。

旧版本已经执行但误判为验证失败的可验证写入，可重新运行其只读后置条件并纠正
状态；creation receipt 丢失等无法通过纯读取重建证据的操作不得自动纠正。任何
纠错路径均禁止重放原写命令。

Dazah Web Agent 收到 Hermes 原生确认后，会把脱敏确认摘要镜像到现有确认列表；
用户点击执行或取消时由后端通过受服务 Token 保护的内部接口回调 Hermes。远端
确认 ID、目标摘要、风险和影响数量可以持久化，CLI 参数、资源 Token 和正文不会
复制到 Dazah 数据库。

## 会话上传附件

Web 与飞书会话上传的受支持附件由 Dazah 后端统一持久化：原文件保存到 Agent
专属 MinIO bucket，数据库只保存会话归属、附件 ID、文件名、MIME、大小、哈希、
版本和受限解析文本。Hermes 临时缓存仍在单轮结束后删除，后续轮次通过可信会话
附件目录恢复，不保存或复用本地临时路径。

模型只能通过 `agent.list_attachments` 和 `agent.read_attachment` 读取当前用户、
当前会话的附件。XLSX/CSV 行新增、修改、删除使用
`agent.mutate_tabular_attachment`，整文件删除使用 `agent.delete_attachment`；这些
写操作统一进入后端确认、权限和审计链路。附件正文、对象存储路径和原始 Base64
不得写入日志、工具目录或普通会话元数据。

每次附件新增、修改和删除都会对 MinIO 结果做对象回读；修改或删除后的数据库刷新
失败时恢复原对象和原版本状态。后续轮次引用持久图片时，从当前用户/会话的对象
重新读取并校验 SHA-256 后再恢复 Base64，文档则恢复受限解析文本，避免仅保存目录
元数据却无法再次读取文件内容。

## 对话基础命令

Web Agent 和飞书原生会话统一支持以下无需模型推理的命令：

- `/new`：归档当前渠道会话并开启一个不继承旧上下文的新对话。
- `/restart`：与 `/new` 相同；兼容别名 `/reset`。
- `/help`：显示当前支持的基础命令。
- `/status`：显示当前渠道、会话和 Agent Backend 协议状态。
- `/tasks`：查询当前用户最近的自动化运行进度、失败状态和错误摘要。
- `/retry <运行ID>`：为本人有权访问的失败运行生成中风险重试确认卡；确认后创建
  新运行，不重放或覆盖原运行。

命令只影响当前用户、当前 Web 会话或当前飞书会话 peer，不会归档其他渠道、其他
群聊或其他用户的会话。基础命令由确定性逻辑直接返回，不能进入模型工具循环。

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

管理员也可在“系统设置 → Livzon Agent管理 → 飞书接入”点击“重启飞书网关”。
该操作经过二次确认和管理员审计，只重建受管的 Gateway 子进程并等待连接恢复，
不会重启整个 Hermes 服务，也不会拉取镜像或部署代码。Hermes 重新部署必须继续
通过受控发布流程完成，管理面板不持有 Docker 或宿主机控制权限。

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

确认卡只能由当前任务实际创建的 pending confirmation 渲染，不能从模型文本或
历史会话推断。新增、修改、删除等请求中，仅读取资源不算完成写操作准备；若本轮
没有调用匹配的写命令并取得真实确认记录，Gateway 必须停止处理并明确返回未生成
确认项，禁止回复“待确认项已生成”或展示旧确认卡。

写操作执行前必须成功写入 Hermes 本地脱敏审计 outbox。审计与资源变更
通知异步投递平台；失败使用持久队列退避补投，不阻塞已完成的飞书操作。
能力搜索、能力详情、工具调用、业务/原生确认、审计收据和主动投递必须携带同一
`trace_id`。飞书 Scope 或资源授权不足时，回复必须分别提示管理员补充应用 API
Scope、将目标资源分享给 Livzon 应用，或同步用户的 Livzon 模块访问范围。
