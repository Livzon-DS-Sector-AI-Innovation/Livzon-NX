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
- EDBO 的 Torch 层；
- Hermes-Lite 的 Lark CLI、上游 Hermes 和 Python 依赖层。

不要为了清理磁盘而随意执行 `docker builder prune`；它会删除这些构建缓存。

## 完整更新

版本号建议使用日期加 Git 短 SHA，且每次必须唯一，例如：

```powershell
.\scripts\deploy-production.ps1 Build -Version 20260813-a1b2c3d
```

该命令会依次完成：

1. 使用本地 Buildx 缓存构建四个 `linux/amd64` 应用镜像；
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
`/login` 的完整代理链路。代理检查失败时，部署流程不会标记成功，并会恢复
部署前配置。

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
