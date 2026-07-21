#!/bin/bash
# Playwright 浏览器环境变量配置
# 使用淘宝镜像下载的 Chromium 浏览器
#
# 用法:
#   source scripts/regulatory_poc/playwright_env.sh
#
# 浏览器来源:
#   https://cdn.npmmirror.com/binaries/chrome-for-testing/148.0.7778.96/linux64/

export PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright-browsers

CHROME_DIR="/tmp/chromium-extracted/chrome-linux64"
HEADLESS_DIR="/tmp/chrome-headless-shell-linux64"

# 验证完整 Chrome
if [ ! -x "$CHROME_DIR/chrome" ]; then
    echo "❌ 完整 Chrome 未找到: $CHROME_DIR/chrome"
    echo ""
    echo "请运行以下命令下载:"
    echo "  cd /tmp"
    echo "  curl -L -o chromium-npm.zip 'https://cdn.npmmirror.com/binaries/chrome-for-testing/148.0.7778.96/linux64/chrome-linux64.zip'"
    echo "  unzip -q chromium-npm.zip -d chromium-extracted"
    exit 1
fi

# 验证 headless shell
if [ ! -x "$HEADLESS_DIR/chrome-headless-shell" ]; then
    echo "⚠️  Headless shell 未找到: $HEADLESS_DIR/chrome-headless-shell"
    echo "   将使用完整 Chrome（功能正常，但体积更大）"
fi

# 验证 Playwright 浏览器缓存目录结构
if [ ! -d "$PLAYWRIGHT_BROWSERS_PATH/chromium-1223" ]; then
    mkdir -p "$PLAYWRIGHT_BROWSERS_PATH/chromium-1223"
    ln -sf "$CHROME_DIR" "$PLAYWRIGHT_BROWSERS_PATH/chromium-1223/chrome-linux64"
fi

if [ ! -d "$PLAYWRIGHT_BROWSERS_PATH/chromium_headless_shell-1223" ]; then
    mkdir -p "$PLAYWRIGHT_BROWSERS_PATH/chromium_headless_shell-1223"
    ln -sf "$HEADLESS_DIR" "$PLAYWRIGHT_BROWSERS_PATH/chromium_headless_shell-1223/chrome-headless-shell-linux64"
fi

echo "✅ Playwright 浏览器路径: $PLAYWRIGHT_BROWSERS_PATH"
echo "✅ Chrome: $CHROME_DIR/chrome"
$CHROME_DIR/chrome --version 2>/dev/null && true
