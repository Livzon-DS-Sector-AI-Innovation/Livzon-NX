# Playwright 浏览器部署指南

本文档说明如何在本地开发、Docker 容器和 Railway 等 PaaS 平台部署 Playwright 浏览器环境。

## 目录结构

```
scripts/regulatory_poc/
├── browser.py              # 统一浏览器启动工具（核心）
├── playwright_env.sh       # Shell 环境变量配置
├── test_cde_nmpa.py        # 采集测试脚本
├── debug_pages.py          # 页面调试脚本
└── PLAYWRIGHT_DEPLOY.md    # 本文档
```

## 快速开始

### 1. 安装 Playwright Python 包

```bash
cd dazah-backend
source .venv/bin/activate
pip install playwright
```

> **注意**: 不需要运行 `playwright install`，我们使用手动下载的 Chrome。

### 2. 下载浏览器二进制文件

```bash
cd /tmp

# 下载完整 Chrome（推荐）
curl -L -o chromium-npm.zip \
  'https://cdn.npmmirror.com/binaries/chrome-for-testing/148.0.7778.96/linux64/chrome-linux64.zip'

# 下载 headless shell（可选）
curl -L -o chromium-headless-shell.zip \
  'https://cdn.npmmirror.com/binaries/chrome-for-testing/148.0.7778.96/linux64/chrome-headless-shell-linux64.zip'

# 解压
unzip -q chromium-npm.zip -d chromium-extracted
unzip -q chromium-headless-shell.zip
```

### 3. 设置环境变量

```bash
cd dazah-backend
source scripts/regulatory_poc/playwright_env.sh
```

### 4. 运行测试

```bash
cd dazah-backend/scripts/regulatory_poc
.venv/bin/python -c "
from browser import create_page
with create_page() as page:
    page.goto('https://example.com')
    print('页面标题:', page.title())
"
```

预期输出: `页面标题: Example Domain`

## 统一启动函数

所有采集脚本必须使用 `browser.py` 中的统一启动函数，确保一致的浏览器配置。

### API

```python
from browser import create_browser, create_page

# 方式一：手动管理
pw, browser = create_browser(headless=True, use_full_chrome=True)
page = browser.new_page()
# ... 操作 ...
browser.close()
pw.stop()

# 方式二：上下文管理器（推荐）
with create_page() as page:
    page.goto("https://example.com")
    print(page.title())

# 自定义视口
with create_page(viewport={"width": 1920, "height": 1080}) as page:
    page.screenshot(path="screenshot.png")
```

### 启动参数说明

`browser.py` 内置以下启动参数，解决容器/沙箱环境的权限限制：

| 参数 | 作用 |
|------|------|
| `--no-sandbox` | 禁用 Chrome 沙箱（容器环境必需） |
| `--disable-setuid-sandbox` | 禁用 setuid 沙箱 |
| `--disable-dev-shm-usage` | 避免 /dev/shm 空间不足 |
| `--disable-gpu` | 禁用 GPU 加速（无头环境不需要） |

## Docker 部署

### Dockerfile

```dockerfile
FROM python:3.12-slim

# 安装 Chrome 依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    unzip \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

# 下载 Chrome
RUN cd /tmp && \
    wget -q https://cdn.npmmirror.com/binaries/chrome-for-testing/148.0.7778.96/linux64/chrome-linux64.zip && \
    unzip -q chromium-npm.zip -d chromium-extracted && \
    rm chromium-npm.zip

# 设置环境变量
ENV PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright-browsers

WORKDIR /app
COPY . .

# 安装 Python 依赖
RUN pip install playwright

# 创建浏览器缓存目录结构
RUN mkdir -p /tmp/playwright-browsers/chromium-1223 && \
    ln -sf /tmp/chromium-extracted/chrome-linux64 \
       /tmp/playwright-browsers/chromium-1223/chrome-linux64

CMD ["python", "scripts/regulatory_poc/test_cde_nmpa.py"]
```

### docker-compose.yml

```yaml
version: '3.8'
services:
  crawler:
    build: .
    environment:
      - PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright-browsers
    volumes:
      - ./results:/app/results
```

### 构建和运行

```bash
docker build -t dazah-crawler .
docker run --rm dazah-crawler
```

## Railway 部署

Railway 支持自定义 Dockerfile，使用上面的 Dockerfile 即可。

### railway.toml

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "python scripts/regulatory_poc/test_cde_nmpa.py"
```

### 环境变量

在 Railway Dashboard → Variables 中添加：

| 变量 | 值 |
|------|------|
| `PLAYWRIGHT_BROWSERS_PATH` | `/tmp/playwright-browsers` |

## 常见问题

### Q: `setsockopt: Operation not permitted`

**原因**: 容器/沙箱限制了 `setsockopt` 系统调用，导致 Chrome crashpad 崩溃。

**解决**: 使用 `browser.py` 的统一启动函数，已内置 `--no-sandbox` 和 `--disable-setuid-sandbox`。

### Q: `Failed to launch browser: /tmp/... no such file`

**原因**: 浏览器二进制文件未下载或路径不对。

**解决**:
```bash
# 检查文件是否存在
ls -la /tmp/chromium-extracted/chrome-linux64/chrome

# 如果不存在，重新下载
source scripts/regulatory_poc/playwright_env.sh
```

### Q: `/dev/shm` 空间不足

**原因**: Docker 默认 `/dev/shm` 只有 64MB。

**解决**: `browser.py` 已内置 `--disable-dev-shm-usage` 参数。如需更大空间：
```bash
docker run --shm-size=256m ...
```

### Q: 中文页面显示乱码

**原因**: 缺少中文字体。

**解决** (Docker):
```dockerfile
RUN apt-get install -y fonts-wqy-zenhei fonts-noto-cjk
```

## 浏览器版本

当前使用的 Chrome 版本: **148.0.7778.96**

下载地址（淘宝镜像）:
- 完整 Chrome: `https://cdn.npmmirror.com/binaries/chrome-for-testing/148.0.7778.96/linux64/chrome-linux64.zip`
- Headless Shell: `https://cdn.npmmirror.com/binaries/chrome-for-testing/148.0.7778.96/linux64/chrome-headless-shell-linux64.zip`

升级版本时，需同步更新 `browser.py` 中的路径和 `playwright_env.sh` 中的目录名。

## 文件清单

部署时需要确保以下文件存在：

```
/tmp/
├── chromium-extracted/
│   └── chrome-linux64/
│       └── chrome                    # 完整 Chrome 二进制
├── chrome-headless-shell-linux64/
│   └── chrome-headless-shell         # Headless shell 二进制
└── playwright-browsers/
    ├── chromium-1223/
    │   └── chrome-linux64 -> /tmp/chromium-extracted/chrome-linux64
    └── chromium_headless_shell-1223/
        └── chrome-headless-shell-linux64 -> /tmp/chrome-headless-shell-linux64
```
