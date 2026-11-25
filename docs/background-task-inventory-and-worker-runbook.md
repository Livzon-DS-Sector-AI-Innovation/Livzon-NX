# Dazah 第一阶段后台任务盘点与回滚手册

盘点日期为 2026-11-24。以下是代码注册基线，供 API 模式和 worker 模式对照。时间按任务配置解释，表中固定钟点使用上海时间。实际生产启用状态、副本、最近成功时间和历史故障待发布维护者在目标环境核对。责任按模块和部署维护角色划分。

## API 调度引擎

统一引擎在 API 进程启动和停止，共 45 个生成器和 3 个静态任务。固定任务、生成器按注册顺序扫描。引擎按进程记录最近触发时间，外部副作用的幂等性需单独核对任务实现。下表每行是一项注册；任务目录文件包含各项查找条件、执行函数和超时定义。[启动与关闭](../dazah-backend/app/main.py) · [引擎](../dazah-backend/app/platform/scheduler/engine.py) · [注册表](../dazah-backend/app/platform/scheduler/registry.py)

| 所有者 | 注册项 | 触发 | 写入或外部动作及恢复入口 |
| --- | --- | --- | --- |
| 平台审计 | audit.user-operation-retention | 02:00 | 清理超期操作记录；按保留策略核对下轮处理量 |
| Agent | agent_automation_scheduler | 5 秒 | 领取已保存的触发窗口并执行；按调度运行记录复核 |
| Agent | agent_push_delivery_scheduler | 5 秒 | 对账网关回执并重试投递；核对持久尝试记录与收件方 |
| 生产 | production.plan_feishu_sync | 10 分钟 | 按到期配置读取飞书并写入生产计划；核对同步结果 |
| 设备 | equipment.inspection_feishu_mirror_sync | 5 分钟 | 巡检增量镜像；核对同步游标 |
| 设备 | equipment.inspection_feishu_mirror_full_sync | 03:10 | 巡检全量镜像；与增量路径一起核对 |
| 设备 | equipment.repair_ledger_mirror_sync | 30 分钟 | 维修台账镜像；核对当前数据版本 |
| 设备 | equipment.spare_part_hardware_sync | 1 小时 | 五金备件同步；核对源表及同步记录 |
| 设备 | equipment.health_snapshot | 03:30 | 写设备健康快照；核对快照日期 |
| 设备 | equipment.spare_part_purchase_scan | 07:30 | 扫描备件采购条件；复核已有申请或提示后再补跑 |
| 设备 | equipment.monthly_health_report | 每月 1 日 08:00 | 生成月度健康报告；按报告月份复核 |
| 能源 | energy.notification_delivery | 30 秒 | 发送通知；按投递记录核对重试及收件方 |
| 仓储 | warehouse.feishu_daily_sync | 15 分钟 | 按启用配置同步仓储数据；核对仓储同步运行状态 |
| 仓储 | warehouse.feishu_analysis | 5 秒 | 消费待执行分析任务；按分析运行 ID 核对 |
| 质量 | quality.feishu_read_daily_sync | 15 分钟检查；上海时间 02:00 后按 UTC 日期判到期 | 更新本地质量镜像与运行记录；资源级租约、数据库提交校验、手工同步 |
| 行政 | administration.feishu_read_sync | 15 分钟 | 更新行政只读镜像；检查资源同步进度 |
| 注册 | registration.certificate_reminders | 09:00 | 检查证书提醒并投递；核对证书及提醒记录 |
| 质量 | quality.change_action_plan_reminders | 1 小时 | 变更行动计划催办；核对行动项与消息 |
| 质量 | quality.trend_alert_escalations | 60 秒 | 处理趋势警报升级；核对处置状态与通知 |
| 质量 | quality.trend_monthly_analysis | 09:00 | 扫描应分析的月份；按分析窗口对账 |
| 质量 | quality.attachment_cache_warmup | 配置时点，示例默认为 02:00 | 预热附件；核对缺失附件和缓存错误 |
| 质量 | quality.supplier_qualification_mirror_sync | 60 秒 | 增量刷新供应商资质镜像 |
| 质量 | quality.supplier_qualification_mirror_full_sync | 02:30 | 全量校核供应商资质镜像 |
| 质量 | quality.inspection_items_mirror_sync | 10 分钟 | 增量刷新检验物品镜像 |
| 质量 | quality.inspection_items_mirror_full_sync | 02:40 | 全量校核检验物品镜像 |
| 质量 | quality.inspection_material_mirror_sync | 10 分钟 | 增量刷新物料检验镜像 |
| 质量 | quality.inspection_material_mirror_full_sync | 02:20 | 全量校核物料检验镜像 |
| 质量 | quality.inspection_finished_mirror_sync | 10 分钟 | 增量刷新成品检验镜像 |
| 质量 | quality.inspection_finished_mirror_full_sync | 02:50 | 全量校核成品检验镜像 |
| 质量 | quality.inspection_instrument_mirror_sync | 10 分钟 | 增量刷新检验仪器镜像 |
| 质量 | quality.inspection_instrument_mirror_full_sync | 03:00 | 全量校核检验仪器镜像 |
| 质量 | quality.items_stock_alert_push | 1 小时 | 检验物品库存预警；核对预警投递记录 |
| HR | hr.offboarding_reminder | 1 小时 | 离职提醒；核对每位员工的触发条件及记录 |
| HR | hr.contract_expiry_reminder | 1 小时 | 合同到期提醒；核对合同和投递状态 |
| HR | hr.contract_sign_reminder | 1 小时 | 合同签署提醒；核对待签记录和投递状态 |
| HR | hr.resume_folder_scanner | 30 秒 | 扫描配置的简历目录并提交处理；核对原文件和 job |
| HR | hr.mail_fetch_scanner | 10 分钟 | 扫描邮件同步配置并处理；核对收件范围和抓取进度 |
| 安全 | safety.regulation_radar_weekly | 周一 08:00 | 扫描法规并生成业务结果；按扫描窗口确认 |
| 安全 | safety.hazard_due_daily | 08:00 | 隐患到期提醒；核对隐患记录与提醒 |
| 安全 | safety.fire_expiry_daily | 08:20 | 消防器材有效期提醒；核对器材和提醒 |
| 安全 | safety.work_permit_gas_due | 15 分钟 | 作业票气体复检催办；核对复检状态和投递 |
| 安全 | safety.cert_expiry_daily | 08:40 | 特种作业证件到期提醒；核对证件和提醒 |
| 安全 | safety.commitment_daily_push | 15 分钟检查 | 安全承诺填报推送；核对站点配置及发送记录 |
| 法规跟踪 | regulatory_tracker.nightly_sync | 00:10 | 抓取法规；按同步任务核对缺页及任务状态 |
| 法规跟踪 | regulatory_tracker.daily_analysis | 02:00 | 分析待处理法规；按文档及分析状态核对 |
| 法规跟踪 | regulatory_tracker.daily_notify | 10:00 | 投递法规摘要；按通知窗口核对 |
| 仓储 | warehouse.feishu_incremental_sync | 10 分钟 | 旧仓储增量同步路径；核对游标及与每日同步的重叠 |
| 仓储 | warehouse.feishu_full_sync | 00:00 | 旧仓储全量同步路径；核对最后完整同步时间 |

安全提醒与法规跟踪注册组、仓储静态注册组有异常记录分支，配置有效和成功注册需分开核对。质量增量及全量镜像以其资源完成时间和结果对账。仓储旧同步与仓储每日同步都从 API 启动，后续迁移时需确认现场启用组合。[质量任务实现](../dazah-backend/app/modules/quality/scheduled.py) · [仓储静态任务](../dazah-backend/app/modules/warehouse/scheduled.py) · [仓储生成器](../dazah-backend/app/modules/warehouse/scheduler.py)

## 独立循环、连接与启动恢复

| 所有者 | 启动入口 | 触发、状态及停止路径 |
| --- | --- | --- |
| 设备 | maintenance_plan_loop | 日切扫描并生成维保工作；设置 stop_maintenance_plan_flag 后取消 |
| 设备 | timeout_scan_loop | 60 秒检查工单超时及超期待验收；设置 stop_timeout_flag 后取消 |
| 设备 | calibration_reminder_loop | 08:30 扫描校验提醒；设置 stop_calibration_reminder_flag 后取消 |
| 平台身份 | member_sync_loop | 飞书成员日同步；设置 stop_member_sync_flag 后取消 |
| HR | hr_member_sync_loop | HR 合同应用成员周期同步，默认间隔 12 小时；取消任务，核对最近同步结果 |
| 仓储 | start_ws_from_db | 按仓储飞书配置建立连接，分发仓储事件；调用仓储 stop_ws |
| 生产 | start_ws_from_db | 按生产飞书配置监听计划、产销及 FL 表事件；有模块 stop_ws，主生命周期未显式调用 |
| 设备 | start_equipment_ws | 凭据启用时建立设备飞书连接；调用 stop_equipment_ws 并取消 |
| 安全 | start_ws | 安全飞书回调，含承诺、表格和作业票；调用 stop_ws 并取消 |
| 安全 | start_sign_relay_poller_task | 网关启用时拉取签署结果，检查签署落库并确认投递；取消轮询任务 |
| HR | start_hr_ws_if_configured | 飞书卡片审批回调；调用 stop_hr_ws |
| 安全 | scheduled_task_loop | 30 秒扫描可配置定时任务；设置停止标志并取消 |
| 安全 | mirror_sync_loop | 15 分钟同步页面镜像，失败短间隔重试；设置停止标志并取消 |
| 生产 | start_mc_sync_scheduler | 10 分钟 MC 表格同步；独立调度器，调用 stop_mc_sync_scheduler |
| 生产 | start_fa_sync_scheduler | 10 分钟 FA 表格同步；独立调度器，调用 stop_fa_sync_scheduler |
| 生产 | start_dr_sync_scheduler | 10 分钟 DR 表格同步；独立调度器，调用 stop_dr_sync_scheduler |
| Agent 与身份 | create_access_scope_sync_engine | 独立引擎每 5 秒按待处理权限 outbox 领取，失败有下次时间；停止引擎并等退出 |

API 启动时另执行 schema 检查、本地用户初始化、权限及菜单填充、采购物料中断状态恢复与陈旧锁处理、质量验证审核孤儿恢复和仓储事件注册。这些是启动操作。生产只读镜像兼容生成器仍在代码中，当前 API 生命周期未注册。飞书连接的线程、回调任务和心跳属于其连接所有者。连接重启前应分别核对回执、最近数据和重复事件处理。[生命周期](../dazah-backend/app/main.py) · [飞书连接管理](../dazah-backend/app/platform/integrations/feishu/ws_client.py) · [读镜像调度](../dazah-backend/app/platform/integrations/feishu/read_scheduler.py)

## 请求触发与 API 外的后台工作

- 请求及事件触发工作按服务入口跟踪。通用 jobs 管理器在本地进程执行、用 Redis 暴露心跳和状态。调用方包括 HR 合同、简历和 AI 考试，身份手工同步，安全检查及应急预案，法规手工同步，研发试验流程，质量计算、异常分析与验证审核。采购物料同步和审计也有请求完成后执行的路径。飞书回调会派生设备、安全和 HR 的任务。核对这些工作的恢复方式时，应从对应记录和 job ID 出发。[进程内作业](../dazah-backend/app/core/jobs.py)
- Hermes 服务生命周期启动飞书平台同步、飞书 Gateway 监督进程和按配置运行的记忆审核 worker。Gateway 进程另有投递轮询和事件任务。Hermes 发布需分别核对 Gateway 接管、投递回执和记忆审核积压。[Hermes 服务生命周期](../Hermes-Lite/services/dazah_agent_service.py) · [Gateway 进程](../Hermes-Lite/services/feishu_gateway_worker.py)
- 单机部署另有备份、恢复演练和流量守卫 timer。迁移是一次性执行。数据库、Redis、MinIO 及容器健康探针由部署管理。生产发布控制器按已部署的镜像覆盖文件跟踪 API、Hermes、前端和可选的质量 worker。[单机运行单元](../deploy/single-host) · [发布控制器](../scripts/cd/controller.py)

## 开发环境切换与回滚

默认 API 注册每日同步。试点采用同一个开发后端镜像，worker 无 HTTP 端口。手工同步继续走质量模块 HTTP 路由及其原权限链。切换前核对开发库授权、Alembic 当前版本与唯一 head，并记录各资源最近完整同步时间、镜像版本和最近运行状态。实际切换时改用本地环境文件管理运行所有者。

1. 在目标开发环境设定 `QUALITY_READ_MIRROR_SCHEDULER=worker`，在试点任务无在途执行时，用原开发 Compose 项目运行 `docker compose --env-file .env.local -f compose.dev.yml up -d --no-deps --force-recreate app`，确认旧实例停止且 `/health` 成功。核对试点任务尚无活跃执行者；如有中断记录，先确认旧实例退出并等资源锁到期。
2. 运行 `docker compose --env-file .env.local -f compose.dev.yml up -d --no-deps quality-read-mirror-worker`。确认 worker 日志只有一个生成器、注册所有者为 worker。以每个资源的成功运行记录和 `last_complete_sync_at` 验收；循环仍在运行或没有到期资源均不能作为同步成功的依据。
3. 出现重复完成、镜像差异、过期覆盖、跨过应执行窗口或 API 异常时，运行 `docker compose --env-file .env.local -f compose.dev.yml stop quality-read-mirror-worker`。等待执行结束并确认所有 worker 已退出。进程强杀后，等该资源锁到期，由下一次执行把遗留 running 转为 failed 并同步；维护门禁会保留强杀进程的活动记录，应按既有运维流程在确认进程及事务终止后对账。
4. 恢复 `QUALITY_READ_MIRROR_SCHEDULER=api`，以原 Compose 项目重新创建 API。确认 API 注册日志、`/health`、最近完整镜像可读，并用到期样本验证 API 完成补跑。对比其余任务清单，历史运行保留供审计。

## 生产发布控制器切换与回滚

生产 Compose 默认由 API 调度。受控切换以发布控制器的 root 专属配置 `/etc/dazah-cd/config.json` 中的 `quality_read_mirror_scheduler` 为准，默认值为 `api`。授权切换时先确认站点 Compose 已包含 `quality-read-mirror-worker`，再把期望模式设为 `worker`，通过下一次尚待验证的发布候选切换。

1. 发布验证在隔离网络上使用迁移验证库和独立 Redis 验证候选 worker。活动门禁保持在启动阶段，允许 schema 检查及健康探针。通过后验收清单将 worker 和 API 锁定到同一个本地后端镜像内容 ID。
2. 发布控制器按当前已生效的覆盖文件识别旧调度归属，关闭流量入口并排空 API 与 worker 共享的活动门禁。旧 worker 如已启用，先收到停止信号，控制器确认容器退出及退出码，再停止其它应用、备份和迁移。
3. 候选覆盖文件将 API 调度归属和 worker 镜像同时锁定。启用时，放流前核对 Docker 健康状态、API 模式、两个容器的实际镜像 ID 与 worker 进程及依赖探针。放流后的发布观察期也检查已启用的 worker。发布完成后，日常流量守卫继续依据在线服务状态决定是否接收流量。
4. 候选在放流前启动或就绪失败时，控制器停止候选 worker，恢复上一版镜像及调度归属，再重新启动并复查。上一版由 API 调度时，worker 保持停止。上一版为 worker 模式时，原版本 worker 必须通过就绪检查。排空、停止或回退验证失败时维持流量关闭，按单机运维手册排查。
5. 现场切换后按质量资源对账最近完整同步时间、镜像版本和运行记录，至少观测一个正常调度窗口。生产飞书窗口观测需随现场切换执行。

[发布控制器](../scripts/cd/controller.py) · [生产 Compose](../compose.yml) · [单机运维手册](runbooks/single-host-operations.md)

## 验证记录

2026-11-24 在开发后端镜像、根目录配置指定的本地专用 PostgreSQL 测试库和一次性 Redis 上验证。飞书使用固定分页样本及可控制的中断。测试库 Alembic 当前版本等于唯一 head。

| 验收项 | 结果 |
| --- | --- |
| 注册与权限 | 代码注册基线共 48 项。模式切换测试验证试点任务在 API 和 worker 之间转移；ASGI 测试验证手工同步的 `sync_config` 权限。 |
| 数据与时间 | 两页样本的记录键、字段与删除标志匹配。覆盖上海时间 02:00 和 UTC 换日，分页失败与 Redis 不可用保留上次完整镜像。 |
| 并发与故障 | 两个独立 worker 进程只提交一份有效镜像。另用两条测试库会话验证延迟候选、手工同步竞争，以及失去锁的旧执行者无法覆盖新结果。 |
| 维护与 API 发布 | 独立 Redis 验证维护期拒绝新扫描。容器中使用真实 API 路由、受控启动生命周期和实际 worker 进程；重启 API 后 `/health` 返回 200，worker 完成本轮。停止 worker 后 API 仍健康。 |
| 回滚 | 强杀 worker 后先观察到 running 记录，由缩短的测试租约模拟到期。切回 API 后得到 success → failed → success 的运行序列，重读为正确镜像。 |
| 调度窗口 | 另以原 15 分钟配置启动 worker，在当日首个符合条件的扫描完成一条到期测试资源。故障演练用缩短的扫描间隔与租约，现场发布需按实际节奏观察。 |

后端定向测试命令在 `dazah-backend/` 运行。维护测试使用一次性 Redis，测试配置需明确指定 `MAINTENANCE_TEST_REDIS_URL`。

```powershell
uv run --no-sync pytest -q tests/modules/quality/test_quality_feishu_worker.py tests/unit/test_feishu_quality_worker.py tests/unit/test_feishu_read_mirror_failures.py tests/unit/test_module_feishu_read_mirror.py tests/unit/test_module_schedulers.py tests/unit/test_scheduler_platform.py tests/unit/test_system_maintenance.py
```

定向测试通过 77 项。Ruff、六个运行代码文件的 Mypy 与开发 Compose 配置检查通过。确认文档引用和试点代码的测试影响策略匹配。试点使用既有表和 API 契约，新增运行模式已同步两份环境示例。真实飞书窗口及现场运行清单留到受控切换验证。

### 生产发布流程隔离验证

2026-11-24，使用从生产 Dockerfile 重建的后端镜像、生产 Compose 的 worker 定义、独立 Compose 项目、根目录配置的专用测试库和一次性 Redis。在线应用用受控容器代替，worker 运行实际入口和 Docker 健康检查。依次核对了 API 默认归属、候选 API 与 worker 的共同镜像内容 ID、Redis 暂停后的探针失败、worker 的 SIGTERM 零退出码、回退到上一版 API，以及恢复上一版 worker 拓扑。演练未触发真实飞书同步。

发布控制器、就绪检查及部署回归测试在 Linux 容器中通过 151 项。该容器没有 Docker CLI，4 项 Compose 渲染测试单独通过。后端定向测试通过 29 项，Ruff 和 Mypy 检查通过。
