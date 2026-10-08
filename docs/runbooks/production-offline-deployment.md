# Dazah 生产离线部署操作手册

本项目生产环境采用“本地构建镜像 + 离线包上传 + Linux 服务器 Compose 部署”。生产服务器不需要访问 Docker Hub、PyPI、npm 或 GitHub 才能启动；Compose 中的生产服务使用 `pull_policy: never`。

## 一次性准备

Windows 本地需要安装并可直接调用：

- Docker Desktop，并启用 Linux containers；
- Docker Buildx；
- OpenSSH 的 `ssh` 和 `scp`；
- 能登录目标服务器的 SSH 密钥。

脚本默认连接：

```text
用户：ubuntu
服务器：150.158.111.91
密钥：%USERPROFILE%\.ssh\id_ed25519
```

如目标服务器或密钥发生变化，可通过参数覆盖。

第一次构建时，脚本会创建名为 `dazah-builder` 的持久 Buildx Builder。后续构建会复用以下缓存层：

- Python/uv 依赖层；
- Node/pnpm 依赖层；
- Hermes-Lite 的 Lark CLI、上游 Hermes 和 Python 依赖层。

不要为了清理磁盘而随意执行 `docker builder prune`；它会删除这些构建缓存。

## 完整更新

版本号建议使用日期加 Git 短 SHA，且每次必须唯一，例如：

```powershell
.\scripts\deploy-production.ps1 Build -Version 20260813-a1b2c3d
```

如果 Docker Desktop 的默认代理不可达，可通过 `-BuildProxy` 临时指定可用的
构建代理，例如 `http://http.docker.internal:3128`；不要为每次构建生成不同的
临时 Dockerfile，以免依赖层缓存失效。

该命令会依次完成：

1. 使用 `docker-bake.hcl` 通过一次 Buildx Bake 共享依赖缓存，构建三个 `linux/amd64` 应用镜像；
2. 使用 `docker save` 生成离线镜像包；
3. 生成 SHA-256 校验文件；
4. 将 Compose、Nginx 和服务器端部署脚本放入同一版本目录；
5. 上传到 `/opt/dazah/releases/<版本>`；
6. 服务器校验并加载镜像；
7. 备份当前 `.env`、Compose 和 Nginx 配置；
8. 更新 `DAZAH_VERSION`，执行 Compose 配置校验和数据库迁移；
9. 等待应用服务健康；
10. 强制重建 Nginx，使单文件挂载重新绑定到本次发布的配置；
11. 检查 Nginx 配置，并通过 HTTPS 实际访问 `/health` 和 `/login`。

192.168.40.251 的 `/opt/dazah/releases` 链接到 `/data/dazah/releases`，上述上传路径
保持可用，实际归档位于数据盘。上传、发布和回退均验证数据盘 UUID 与挂载身份；
数据盘异常时停止操作，避免向系统盘的空挂载目录写入发布包。

构建缓存要求：固定使用持久的 `dazah-builder`，不要执行全量 builder prune；后端
uv、前端 pnpm/Next.js 和 Hermes uv 依赖均使用 BuildKit cache mount。只有基础镜像
Digest 或 lock 文件变化时，依赖层才需要重新构建。

生产 `.env` 永远只保留在服务器，脚本不会下载、覆盖或打印它。

## 分步操作

只构建并保留本地发布包：

```powershell
.\scripts\deploy-production.ps1 Build `
  -Version 20260813-a1b2c3d `
  -SkipUpload `
  -SkipDeploy
```

使用已生成的发布包上传并部署：

```powershell
.\scripts\deploy-production.ps1 Deploy -Version 20260813-a1b2c3d
```

发布和回滚默认提前预告 180 秒，参数 `-NoticeSeconds` 支持 0–3600 秒。
预告期间允许用户保存；0 秒仅用于已经人工完成预告的维护窗口。
随后关闭公共入口并等待请求、业务任务排空；未排空则保持维护并中止发布。
恢复旧容器时先放行初始化任务，健康、代理、迁移版本及排空检查全部通过后才恢复用户操作。
当前页面不会因维护自动跳转或刷新；写操作结果待确认时先查询并核对业务记录，禁止自动补发。
首次上线的版本兼容步骤、异常任务登记处置和剩余边界见 [单服务器 CD 与恢复](single-host-cd.md)。

如果只需要查看线上状态：

```powershell
.\scripts\deploy-production.ps1 Status
```

验证当前版本：

```powershell
.\scripts\deploy-production.ps1 Verify
```

## 回滚

回滚到已上传的版本：

```powershell
.\scripts\deploy-production.ps1 Rollback -Version 20260813-67bf77b
```

服务器会重新加载目标版本镜像（如果镜像仍在本地则直接复用），切换 `DAZAH_VERSION` 并重新启动服务。

每次更新前的 `.env`、Compose 和 Nginx 配置会备份到：

```text
/opt/dazah/backups/deploy/<UTC 时间>-<旧版本>/
```

## 重要回滚限制

应用镜像和数据库迁移不是同一个回滚单元。脚本可以安全切换应用镜像，但不会自动逆向 Alembic 迁移。

因此：

- 兼容性迁移可以正常跟随发布执行；
- 破坏性数据库变更必须先设计 downgrade 或数据库备份方案；
- 发生数据库结构不兼容时，不要反复执行应用回滚，应先恢复数据库或提供兼容修复版本。

更新脚本不会执行 `docker compose down -v`，不会删除 PostgreSQL、Redis、MinIO、上传文件或 Hermes 数据卷。

## Nginx 502 防护与排查

生产 Nginx 通过单文件 bind mount 加载 `nginx.default.conf`。部署脚本会原子替换
宿主机文件；已运行的容器仍可能持有旧文件 inode，因此仅执行
`nginx -s reload` 不能保证加载新配置。部署和回滚流程必须强制重建 Nginx
容器，禁止将这一步改回普通 reload。

同时，Nginx upstream 使用 Docker 内置 DNS（`127.0.0.11`）动态解析 `app`
和 `frontend`。应用容器重建并更换 IP 后，Nginx 会自动更新 upstream 地址。

若部署命令返回成功但页面出现 502，先执行：

```powershell
.\scripts\deploy-production.ps1 Verify -NoSudo
```

`Verify` 会检查容器健康、Nginx 配置，以及通过 Nginx 访问 `/health` 和
`/login` 的完整代理链路。代理检查失败时，部署流程不会标记成功；维护模式保持
开启，修复后通过完整验证才恢复访问。

## 维护模式（2026-09-30）

正式入口统一挂载 `/var/lib/dazah-cd/public`。维护标记存在时，HTTP 和 HTTPS
在 server 层阻断所有路由及请求方法，返回中文维护界面、503、`Retry-After: 15`
和 `Cache-Control: no-store`；请求不会转发给业务服务。维护页每 15 秒检查恢复
状态，恢复后进入登录页，不自动重放原有写请求。正常 HTML 页面注入同源状态
检测脚本，每 5 秒通过只读标记探针自动切换维护界面；探针不访问业务服务。
后台标签页恢复可见时立即检查。首次安装前已打开的页面需刷新一次才能加载检测。
已发出的请求需先排空，不能把响应阻断理解为撤销已完成的业务操作；切换页面可能
丢失尚未提交的表单，计划维护应预留保存时间。

新发布包必须包含维护配置、排空探针配置及迁移策略；缺少这些文件的旧包会被拒绝，
应重新生成新版本发布包，不能修改已有不可变版本。Deploy/Rollback 自动开启维护，
确认代理已返回 503，再排空请求、停止应用写入源、执行经过审查的迁移目标，随后
启动应用。开启维护后的失败和中断保留维护状态，不因配置恢复而自动开放流量。
有 `compose.release.yml` 的站点由 CD 控制器发布，手工发布脚本拒绝覆盖其固定镜像。

解除维护必须通过所有依赖和应用容器状态、后端与 Hermes `/health`、内部依赖
readiness、Nginx 配置及 `/health`、`/login` 代理路由、唯一代码 head 与数据库
revision 检查。内部探针通过容器 loopback 的 8090 端口使用同一套路由；该端口
不映射到宿主机，公开 URL 和请求头无法绕过维护。迁移策略中已审查的临时 hold
只适用于其精确源码 head 和允许的数据库 revision，不能用于忽略任意版本漂移。
本次维护功能安装只读取迁移版本，不执行正式库迁移。

手工重建前后使用同一维护入口：

```bash
sudo /opt/dazah/current/deploy-production.sh maintenance-on
# 执行已授权的维护操作；不要使用 down -v。
sudo /opt/dazah/current/deploy-production.sh maintenance-off
```

```powershell
.\scripts\deploy-production.ps1 MaintenanceOn -Server 192.168.40.251 -SshUser livzon
.\scripts\deploy-production.ps1 MaintenanceOff -Server 192.168.40.251 -SshUser livzon
```

`dazah-traffic-guard.timer` 每次检查结束后约 2 秒再次检测。发现依赖、应用、代理
容器缺失或不健康，或者迁移容器运行时，自动开启维护；只在完整检查通过后解除
自己开启的维护。人工/发布开启的维护、失败发布状态和 watchdog blocked 状态
不会被巡检解除。巡检不启动或重启业务容器，不启用 CD/watchdog 的发布和恢复。
绕过维护入口直接执行 Docker 操作存在检测间隔；计划操作必须先开启维护。
单节点 Nginx 自身重建/停止期间无法提供维护页面，连接会短暂中断；如需此时仍
持续展示页面，需要独立于被重建栈的外层代理。

服务器已安装并启用维护巡检，正式入口已验证 98 个 HTTP/HTTPS 路由与方法组合
均被阻断，解除后 `/health` 和 `/login` 正常。当前业务镜像和数据库未变更，
CD/watchdog timer 继续关闭。安装备份位于
`/opt/dazah/backups/maintenance-20260930-082231`（初始安装）和
`/opt/dazah/backups/maintenance-observer-20260930-082752`（页面检测），只包含本次替换的部署配置和
控制程序，不包含生产环境文件。回退此功能前先停止维护巡检，恢复备份配置并
重建 Nginx；回退会失去自动维护保护。

验证记录：

- 在无网络、工作区只读挂载的 `dazah/backend:cd-verify-dev` 开发镜像内执行
  `/app/.venv/bin/python -m pytest -p no:cacheprovider scripts/tests/test_cd_controller.py scripts/tests/test_cd_stage_site.py scripts/tests/test_production_proxy_deployment.py scripts/tests/test_maintenance_browser.py -q`：
  106 passed、2 skipped。跳过的是显式 Docker 集成和该镜像缺少 Node 的浏览器脚本验证，均在下项单独执行。
- 本机设置 `RUN_CD_CONTAINER_TESTS=1`，执行
  `python -m pytest scripts/tests/test_cd_stage_site.py scripts/tests/test_maintenance_browser.py -q`：
  5 passed，含真实隔离 Nginx、流式容量、HTML 脚本注入、维护阻断和恢复，以及 Node 状态切换验证。
- `bash -n scripts/deploy-production-remote.sh`（通过隔离开发容器执行）、PowerShell
  Parser、`git diff --check`：通过。测试影响策略对本次 controller/stage_site 未提交
  改动与对应测试的映射检查通过；没有执行 Git 提交，提交历史门禁需在提交时再运行。
- 服务器 `python3 /opt/dazah/control/controller.py verify`：通过；当前唯一源码 head
  与数据库 revision 均为 `d7e8f9a1b2c3`，维护标记已关闭，巡检 timer active。
- 未对正式数据库执行迁移、破坏性故障演练或业务全量测试；本次只修改代理和部署
  控制层。未修改 OpenAPI、环境变量或业务镜像，后续生成发布包会增加维护配置文件。

## 服务器端直接操作

如果本地电脑暂时不可用，也可以 SSH 到服务器执行：

```bash
sudo /opt/dazah/current/deploy-production.sh status
sudo /opt/dazah/current/deploy-production.sh verify
sudo /opt/dazah/current/deploy-production.sh rollback 20260813-67bf77b
```

## 服务器镜像缓存

服务器会保留已加载的应用镜像和基础设施镜像。后续回滚到仍存在于服务器的版本时，不需要重新下载镜像包。

本地构建缓存和服务器运行镜像缓存用途不同：

- 本地 Buildx 缓存减少构建时间；
- 服务器镜像缓存支持离线启动和快速回滚；
- 删除服务器旧镜像前，应至少保留当前版本和上一个稳定版本。
