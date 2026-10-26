# 单机运维：备份、恢复演练与维护闸门

本文件只描述生产服务器上**仍在运行**的常驻运维能力。自动发布（单机 CD 控制器调度、
候选登记、自托管 runner）已于 2026-10-26 退役，发布改由运维按
[生产离线部署](production-offline-deployment.md) 手工执行。

## 仍然运行的部分

| 单元 | 作用 | 触发 |
| --- | --- | --- |
| `dazah-backup.timer` | 每日在线备份：PostgreSQL、Redis RDB、持久卷与当前配置 | 每日 01:00 |
| `dazah-restore-drill.timer` | 在独立容器恢复最近一份日备份，验证可恢复性 | 每月 1 日 00:00 |
| `dazah-traffic-guard.timer` | 服务不可用或部署持锁时的维护闸门与恢复检查 | 约每 3 秒 |

对应的实现仍在 `/opt/dazah/control/controller.py`（root 管理，发布包不能覆盖）。
备份内容写入 `/data/dazah/backups/<kind>-<UTC 时间戳>/`，权限 0700。

## 常用命令

```bash
sudo python3 /opt/dazah/control/controller.py status
sudo python3 /opt/dazah/control/controller.py backup      # 立即备份
sudo python3 /opt/dazah/control/controller.py drill       # 立即恢复演练
sudo python3 /opt/dazah/control/controller.py verify      # 就绪检查
```

事件写入 `/var/lib/dazah-cd/events.jsonl`，`backup_complete`、`operation_failed`
等记录可直接用于巡检。

## 备份判定与保留

- 成功以 `manifest.json` 与每个文件的 SHA-256 为准；没有 manifest 的目录视为失败或未完成。
- 归档使用 tar：退出码 1 表示「读取期间文件变化」（在线卷常态），只要归档能被
  `tar -tzf` 完整列出就判定成功，并在 `manifest.json` 的
  `archive_attempts.<文件名>.changed_during_read` 记录是否发生过在线变化；
  退出码 ≥ 2 视为致命错误，立即失败。
- 在线备份标记 `online_independent_copies`，不保证数据库与对象文件处于同一时间点。
- 保留最近 7 份日备份、4 周各一份、6 个月各一份、最近 3 次部署前备份，以及当前/上一版本
  恢复点，取并集；只对逐文件校验通过的备份执行保留清理。
- 损坏或未完成的目录保留供诊断，不自动删除，也不计入可恢复备份，持续增长需人工处理。

## 维护闸门

`dazah-traffic-guard` 在服务不健康或部署持有 `/var/lock/dazah-deploy.lock` 时关闭公共入口，
并在恢复条件满足后重新开放。手工发布期间它记录 `another operation holds deployment lock`
属于预期现象。

## 候选目录

`/var/lib/dazah-candidates` 原先由自托管 runner 写入、供控制器调度使用。runner 与调度器
退役后不再产生新文件；目录已清空，候选登记与清理 timer 一并移除。
`controller.py prune-candidates` 保留为手工工具，用于日后需要时手动清理残留的 `<SHA>.json`。

## 已移除的部分

- `Jenkinsfile`、`scripts/jenkins/`、Jenkins 运行手册：从未落地的备选 CI 方案。
- 单机 CD 控制器调度、`dazah-cd.timer`、`dazah-watchdog.timer`、`dazah-build.*`、
  `dazah-runner-loopback.service`、候选登记与清理 timer、GitHub 自托管 runner。
- `stage_site.py`、`compose.single-host.yml` 与两份 nginx guard 配置：只服务于自动发布的
  站点候选生成与受控资源覆盖，手工发布链路不使用它们。

发布、回滚与环境准备仍按 [生产离线部署](production-offline-deployment.md) 执行；
`scripts/cd/readiness.py` 与 `scripts/cd/conversion_limit.py` 仍被前后端镜像引用，
不在退役范围内。
