#!/usr/bin/env python3
"""
统一 Playwright 浏览器启动工具

提供一致的浏览器启动配置，解决沙箱/容器环境中的权限问题。

用法:
    from browser import create_browser, create_page

    # 方式一：手动管理生命周期
    pw, browser = create_browser()
    page = browser.new_page()
    # ... 操作 ...
    browser.close()
    pw.stop()

    # 方式二：上下文管理器（推荐）
    with create_page() as page:
        page.goto("https://example.com")
        print(page.title())
"""

import os
from contextlib import contextmanager
from playwright.sync_api import sync_playwright

# 浏览器二进制文件路径
CHROME_EXECUTABLE = "/tmp/chromium-extracted/chrome-linux64/chrome"
HEADLESS_SHELL = "/tmp/playwright-browsers/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell"

# Playwright 浏览器缓存路径
BROWSERS_PATH = "/tmp/playwright-browsers"

# 通用启动参数：解决容器/沙箱环境的权限限制
LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


def _setup_env():
    """设置 Playwright 环境变量"""
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = BROWSERS_PATH


def create_browser(headless=True, use_full_chrome=True):
    """
    创建并返回 (playwright_instance, browser) 元组。

    Args:
        headless: 是否无头模式，默认 True
        use_full_chrome: 优先使用完整 Chrome 而非 headless shell

    Returns:
        (playwright_instance, browser)
    """
    _setup_env()
    pw = sync_playwright().start()

    executable_path = CHROME_EXECUTABLE if use_full_chrome else None

    browser = pw.chromium.launch(
        headless=headless,
        executable_path=executable_path,
        args=LAUNCH_ARGS,
    )
    return pw, browser


@contextmanager
def create_page(headless=True, use_full_chrome=True, viewport=None):
    """
    上下文管理器：自动创建和关闭浏览器。

    用法:
        with create_page() as page:
            page.goto("https://example.com")
            print(page.title())
    """
    pw, browser = create_browser(headless=headless, use_full_chrome=use_full_chrome)
    try:
        ctx_opts = {}
        if viewport:
            ctx_opts["viewport"] = viewport
        context = browser.new_context(**ctx_opts)
        page = context.new_page()
        yield page
        context.close()
    finally:
        browser.close()
        pw.stop()
